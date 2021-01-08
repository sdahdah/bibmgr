import os
import sys
import argparse
import pathlib
import biblib.bib
import biblib.algo
import configparser
import string
import shutil
import collections
import logging


def main():
    # Figure out config path using environment variables
    if os.name == 'posix':
        xdg_config_home_raw = os.environ.get('XDG_CONFIG_HOME')
        if xdg_config_home_raw is None:
            home = pathlib.Path(os.environ.get('HOME'))
            xdg_config_home = home.joinpath('.config')
        else:
            xdg_config_home = pathlib.Path(xdg_config_home_raw)
        default_conf_path = xdg_config_home.joinpath('bibmgr/bibmgr.conf')
    else:
        # TODO Windows is untested...
        localappdata = pathlib.Path(os.environ.get('LOCALAPPDATA'))
        default_conf_path = localappdata.joinpath('bibmgr/bibmgr.conf')

    # TODO Figure out help and prog
    parser = argparse.ArgumentParser(description='')
    subparsers = parser.add_subparsers()

    # Shared arguments
    parser.add_argument('-d', '--dry-run', action='store_true', dest='dry_run',
                        help='')
    parser.add_argument('-v', '--verbose', action='store_true', dest='verbose',
                        help='')
    parser.add_argument('-c', '--config', metavar='CONFIG', type=str,
                        dest='conf_path', default=default_conf_path,
                        help='Path to configuration file (*.conf)')
    parser.add_argument('-l', '--library', metavar='LIBRARY', type=str,
                        dest='lib', default=None,
                        help='Name of library to use')
    # Echo subcommand
    echo_parser = subparsers.add_parser('echo', help='Print BibTeX file.')
    echo_parser.set_defaults(func=echo)
    # Org subcommand
    org_parser = subparsers.add_parser('org', help='')
    org_parser.set_defaults(func=org)
    # Link subcommand
    link_parser = subparsers.add_parser('link', help='')
    link_parser.add_argument('pdf', metavar='PDF', type=str, help='')
    link_parser.add_argument('-k', '--key', metavar='KEY', type=str,
                             default=None, help='')
    link_parser.set_defaults(func=link)

    # Parse arguments
    args = parser.parse_args()

    # Set logging level
    logging_level = logging.INFO if args.verbose else logging.WARNING
    formatter = '[%(asctime)s] %(levelname)s: %(message)s'
    logging.basicConfig(format=formatter, level=logging_level)

    # Load and parse config file
    if not pathlib.Path(args.conf_path).exists():
        logging.critical(f'Specified config file `{args.conf_path}` does not '
                         'exist.')
        sys.exit(1)
    if not pathlib.Path(args.conf_path).is_file():
        logging.critical(f'Specified config file `{args.conf_path}` is not a '
                         'file.')
        sys.exit(1)
    else:
        conf = configparser.ConfigParser()
        conf.read(args.conf_path)

    # Choose default library if none is specified
    if args.lib is None:
        selected_lib = conf['config']['default_library']
    else:
        selected_lib = args.lib

    # Create Library object
    lib = Library(conf[selected_lib]['bibtex_file'],
                  conf[selected_lib]['storage_path'],
                  conf[selected_lib]['default_group'],
                  conf.getint('config', 'filename_length'),
                  conf.getint('config', 'key_length'),
                  conf.getint('config', 'wrap_width'),
                  args.dry_run)

    # Run subcommand. If no subcommand was specified, print help message.
    try:
        args.func(lib, args)
    except AttributeError:
        parser.print_help()


def echo(lib, args):
    lib.open_bib_db()
    for entry in lib.db.values():
        print(entry.to_bib(wrap_width=lib.wrap_width), end='\n\n')


def org(lib, args):
    # TODO DONT MOVE IF EVERYTHING IS IN ORDER
    lib.open_bib_db()
    # Create new group folders
    lib.create_missing_groups()
    # Rename files according to metadata
    lib.rename_according_to_bib()
    # Move files to correct groups
    lib.move_according_to_bib()
    # Update keys according to metadata
    lib.rekey_according_to_bib()
    # Write new bib file
    lib.write_bib_file()


def link(lib, args):
    lib.open_bib_db()
    lib.link_file(args.pdf, args.key)
    lib.write_bib_file()


class Library:

    def __init__(self, bibtex_file, storage_path, default_group,
                 filename_length, key_length, wrap_width, dry_run):
        # Paths and settings
        self.bibtex_file = pathlib.Path(bibtex_file)
        self.bibtex_bak_file = pathlib.Path(bibtex_file + '.bak')
        self.storage_path = pathlib.Path(storage_path)
        self.default_group = default_group
        self.filename_length = filename_length
        self.key_length = key_length
        self.wrap_width = wrap_width
        self.dry_run = dry_run
        self.db = None

    def create_missing_groups(self):
        for entry in self.db.values():
            # If group doesn't exist, set it to the default
            if 'groups' in entry.keys():
                group_path = self.storage_path.joinpath(entry['groups'])
            else:
                group_path = self.storage_path.joinpath(self.default_group)
            # If folder does not already exist, create it.
            if not group_path.exists():
                if self.dry_run:
                    logging.info(f'(Dry run) Creating `{group_path}`.')
                else:
                    logging.info(f'Creating `{group_path}`.')
                    group_path.mkdir()
            else:
                logging.info(f'Directory `{group_path}` already exists. '
                             'Skipping.')

    def rename_according_to_bib(self):
        for key, entry in zip(self.db.keys(), self.db.values()):
            # Skip entries with invalid files.
            # Logging takes place inside helper function.
            if not _entry_file_is_valid(key, entry):
                continue
            filename = _entry_string(entry, self.filename_length)
            if filename == '':
                logging.warn('Cannot generate new file name for entry with '
                             f'key `{key}`. Skipping.')
                continue
            pdf_path = pathlib.Path(entry['file'])
            ext = ''.join(pdf_path.suffixes)
            new_path = pdf_path.parent.joinpath(filename + ext)
            # Double check if path points to a file to avoid accidentally
            # moving directory. `is_file()` is the most important check here.
            self.move_pdf_file(pdf_path, new_path)
            entry['file'] = str(new_path)

    def move_according_to_bib(self):
        for key, entry in zip(self.db.keys(), self.db.values()):
            # Skip entries with invalid files.
            # Logging takes place inside helper function.
            if not _entry_file_is_valid(key, entry):
                continue
            # Add default group
            if 'groups' not in entry.keys():
                entry['groups'] = self.default_group
            pdf_path = pathlib.Path(entry['file'])
            new_path = self.storage_path.joinpath(
                entry['groups']).joinpath(pdf_path.name)
            # Double check if path points to a file to avoid accidentally
            # moving directory. `is_file()` is the most important check here.
            self.move_pdf_file(pdf_path, new_path)
            entry['file'] = str(new_path)

    def rekey_according_to_bib(self):
        new_db = collections.OrderedDict()
        for key, entry in zip(self.db.keys(), self.db.values()):
            new_key = _entry_string(entry, self.key_length, words_from_title=1)
            # If new key is empty, don't change it
            if new_key == '':
                logging.warn('Cannot generate new key for entry with key '
                             f'`{key}`. Skipping.')
                new_key = key
            # If there's a duplicate, change the name
            while new_key in new_db.keys():
                logging.warn(f'Two entires share the key `{key}`. '
                             'Appending `_dup` to second entry.')
                new_key += '_dup'
            entry.key = new_key
            new_db[new_key] = entry
        self.db = new_db

    def link_file(self, pdf, key=None):
        # Read path and set default key
        pdf_path = pathlib.Path(pdf)
        if key is None:
            key = pdf_path.stem
        # Check validity of PDF path, then link if valid.
        if not pdf_path.exists():
            logging.warning(f'{pdf_path} does not exist. Not linking.')
        elif not pdf_path.is_file():
            logging.warning(f'{pdf_path} is not a file. Not linking.')
        else:
            if key.lower() in self.db:
                self.db[key.lower()]['file'] = str(pdf_path.resolve())
            else:
                self.db[key.lower()] = biblib.bib.Entry(
                    [('file', str(pdf_path.resolve()))], key=key.lower(),
                    typ='misc')

    def open_bib_db(self):
        """Opens and reads contents of BibTeX file."""
        logging.info(f'Opening `{self.bibtex_file}`.')
        with open(self.bibtex_file, 'r') as bib:
            self.db = biblib.bib.Parser().parse(bib).get_entries()

    def write_bib_file(self):
        """Writes BibTeX dictionary to file.
        """
        if self.dry_run:
            logging.info(f'(Dry run) Deleting `{self.bibtex_bak_file}`.')
            logging.info(f'(Dry run) Moving `{self.bibtex_file}` to '
                         f'`{self.bibtex_bak_file}`.')
            logging.info(f'(Dry run) Writing `{self.bibtex_file}`.')
        else:
            # Delete .bak file if it exists
            logging.info(f'Deleting `{self.bibtex_bak_file}`.')
            self.bibtex_bak_file.unlink(missing_ok=True)
            # Rename .bib file to .bib.bak
            logging.info(f'Moving `{self.bibtex_file}` to '
                         f'`{self.bibtex_bak_file}`.')
            if self.bibtex_file.exists():
                self.bibtex_file.rename(self.bibtex_bak_file)
            # Write new .bib file
            logging.info(f'Writing `{self.bibtex_file}`.')
            with open(self.bibtex_file, 'a') as bib:
                for entry in self.db.values():
                    bib.write(entry.to_bib(wrap_width=self.wrap_width))
                    bib.write('\n\n')

    def move_pdf_file(self, old_file, new_file):
        if self.dry_run:
            logging.info(f'(Dry run) Moving `{old_file}` to `{new_file}`.')
        elif not old_file.exists():
            logging.warning(f'{old_file} does not exist. Not moving.')
        elif not old_file.is_file():
            logging.warning(f'{old_file} is not a file. Not moving.')
        else:
            logging.info(f'Moving `{old_file}` to `{new_file}`.')
            shutil.move(old_file, new_file)


def _entry_file_is_valid(key, entry):
    if 'file' not in entry.keys():
        logging.warn(f'No file in entry with key `{key}`. Skipping.')
        return False
    if entry['file'] == '':
        logging.warn(f'File field in entry with key `{key}` is '
                     'empty. Skipping.')
        return False
    if not pathlib.Path(entry['file']).exists():
        logging.warn(f"File `{entry['file']}` in entry with key "
                     f"`{key}` does not exist. Skipping.")
        return False
    if not pathlib.Path(entry['file']).is_file():
        logging.warn(f"File `{entry['file']}` in entry with key "
                     f"`{key}` is not a file. Skipping.")
        return False
    return True


def _entry_string(entry, max_length, words_from_title=None):
    """Return string with format author_year_title."""
    string_components = []
    if 'author' in entry.keys():
        # Last name of first author
        string_components.append(_clean_string(
            biblib.algo.parse_names(entry['author'])[0].last))
    if 'year' in entry.keys():
        string_components.append(_clean_string(entry['year']))
    if 'title' in entry.keys():
        if words_from_title is None:
            # Take all of title
            string_components.append(_clean_string(entry['title']))
        else:
            # Take up to `words_from_title` words from title
            string_components.append(_clean_string(
                '_'.join(entry['title'].split(' ')[:words_from_title])))
    return '_'.join(string_components)[:max_length]


def _clean_string(s):
    valid = string.ascii_lowercase + string.digits + '_'
    s_nospace = s.lower().replace(' ', '_')
    s_clean = ''.join(char for char in s_nospace if char in valid)
    return s_clean
