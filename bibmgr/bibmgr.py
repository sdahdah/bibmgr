import os
import argparse
import pathlib
import biblib.bib
import biblib.algo
import configparser
import string
import shutil
import collections


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
        # If on Windows, must specify manually for now
        default_conf_path = ''

    # TODO Figure out help and prog

    parser = argparse.ArgumentParser(description='')
    subparsers = parser.add_subparsers()

    # Shared arguments
    parser.add_argument('-c', '--config', metavar='CONFIG', type=str,
                        dest='conf_path', default=default_conf_path,
                        help='path to default configuration file (*.conf)')
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

    # Load and parse config file
    if pathlib.Path(args.conf_path).exists():
        conf = configparser.ConfigParser()
        conf.read(args.conf_path)
    else:
        raise FileNotFoundError(args.conf_path)

    # Choose default library if none is specified
    if args.lib is None:
        selected_lib = conf['config']['default_library']
    else:
        selected_lib = args.lib

    # Create Library object
    lib = Library(conf[selected_lib]['bibtex_file'],
                  conf[selected_lib]['storage_path'],
                  conf.getint('config', 'filename_length'),
                  conf.getint('config', 'key_length'),
                  conf.getint('config', 'wrap_width'))

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
    # Make sure desired PDF exists
    # TODO Also check that it's a file not a directory
    pdf_path = pathlib.Path(args.pdf)
    if not pdf_path.exists():
        raise FileNotFoundError(args.pdf)
    # Link file with filename as default key
    lib.link_file(pdf_path, pdf_path.stem if args.key is None else args.key)
    lib.write_bib_file()


class Library:

    def __init__(self, bibtex_file, storage_path, filename_length, key_length,
                 wrap_width):
        # Paths and settings
        self.bibtex_file = pathlib.Path(bibtex_file)
        self.bibtex_bak_file = pathlib.Path(bibtex_file + '.bak')
        self.storage_path = pathlib.Path(storage_path)
        self.filename_length = filename_length
        self.key_length = key_length
        self.wrap_width = wrap_width
        self.db = None

    def create_missing_groups(self):
        for entry in self.db.values():
            group_path = self.storage_path.joinpath(entry['groups'])
            try:
                group_path.mkdir()
            except FileExistsError:
                pass  # Folder exists, don't need to do anything

    def rename_according_to_bib(self):
        for key, entry in zip(self.db.keys(), self.db.values()):
            # Take last name of first author
            name = _clean_string(
                biblib.algo.parse_names(entry['author'])[0].last)
            year = _clean_string(entry['year'])
            title = _clean_string(entry['title'])
            filename = (name + '_' + year + '_' + title)[:self.filename_length]
            if filename == '':
                # TODO DO SOMETHING MORE GRACEFUL?
                raise RuntimeError(f"New file name for key '{key}' is empty, "
                                   f"cannot rename.")
            if 'file' not in entry.keys():
                # TODO Maybe warn here?
                continue
            pdf_path = pathlib.Path(entry['file'])
            ext = ''.join(pdf_path.suffixes)
            new_path = pdf_path.parent.joinpath(filename + ext)
            # Double check if path points to a file to avoid accidentally
            # moving directory. `is_file()` is the most important check here.
            # TODO Maybe encapsulate this
            if (('file' not in entry.keys()) or (entry['file'] == '')
                    or (not pdf_path.exists()) or (not pdf_path.is_file())):
                # TODO Maybe warn here?
                continue
            shutil.move(pdf_path, new_path)
            entry['file'] = str(new_path)

    def move_according_to_bib(self):
        for key, entry in zip(self.db.keys(), self.db.values()):
            if 'file' not in entry.keys():
                # TODO Maybe warn here?
                continue
            pdf_path = pathlib.Path(entry['file'])
            new_path = self.storage_path.joinpath(
                entry['groups']).joinpath(pdf_path.name)
            # Double check if path points to a file to avoid accidentally
            # moving directory. `is_file()` is the most important check here.
            # TODO Maybe encapsulate this
            if (('file' not in entry.keys()) or (entry['file'] == '')
                    or (not pdf_path.exists()) or (not pdf_path.is_file())):
                # TODO Maybe warn here?
                continue
            shutil.move(pdf_path, new_path)
            entry['file'] = str(new_path)

    def rekey_according_to_bib(self):
        new_db = collections.OrderedDict()
        for key, entry in zip(self.db.keys(), self.db.values()):
            # Take last name of first author
            name = _clean_string(
                biblib.algo.parse_names(entry['author'])[0].last)
            year = _clean_string(entry['year'])
            title = _clean_string(entry['title'].split(' ')[0])
            new_key = (name + '_' + year + '_' + title)[:self.key_length]
            # If new key is empty, don't change it
            if new_key == '':
                # TODO Print warning
                new_key = key
            # If there's a duplicate, change the name
            while new_key in new_db.keys():
                # TODO Print warning
                new_key += '_dup'
            entry.key = new_key
            new_db[new_key] = entry
        self.db = new_db

    def link_file(self, pdf_path, key):
        # def gen_db_with_blank_entry(self, key, file):
        #     entry = (
        #         f'@misc{{{key},\n'
        #         f'  file = {{{file}}},\n'
        #         f'}}'
        #     )
        if key.lower() in self.db:
            self.db[key.lower()]['file'] = str(pdf_path.resolve())
        else:
            self.db[key.lower()] = biblib.bib.Entry(
                [('file', str(pdf_path.resolve()))], key=key.lower(),
                typ='misc')

    def open_bib_db(self):
        """Opens and reads contents of BibTeX file."""
        with open(self.bibtex_file, 'r') as bib:
            self.db = biblib.bib.Parser().parse(bib).get_entries()

    def write_bib_file(self):
        """Writes BibTeX dictionary to file.
        """
        # Delete .bak file if it exists
        self.bibtex_bak_file.unlink(missing_ok=True)
        # Rename .bib file to .bib.bak
        if self.bibtex_file.exists():
            self.bibtex_file.rename(self.bibtex_bak_file)
        # Write new .bib file
        with open(self.bibtex_file, 'a') as bib:
            for entry in self.db.values():
                bib.write(entry.to_bib(wrap_width=self.wrap_width))
                bib.write('\n\n')


def _clean_string(s):
    valid = string.ascii_lowercase + string.digits + '_'
    s_nospace = s.lower().replace(' ', '_')
    s_clean = ''.join(char for char in s_nospace if char in valid)
    return s_clean
