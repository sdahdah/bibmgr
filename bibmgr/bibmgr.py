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
    """Bibmgr's main method.

    Parses arguments and config, creates a Library object, then delegates
    action to one of its subcommands.
    """

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

    # Create parser and subparsers
    parser = argparse.ArgumentParser(
        description='bibmgr is a CLI reference manager based around BibTeX')
    subparsers = parser.add_subparsers()
    # Shared arguments for all subcommands
    parser.add_argument('-v', '--verbose', action='store_true', dest='verbose',
                        help='show detailed output')
    parser.add_argument('--debug', action='store_true', dest='debug',
                        help='show very detailed output with timestamps '
                             '(stronger version of `--verbose`)')
    parser.add_argument('--dry-run', action='store_true', dest='dry_run',
                        help='run command without moving or writing to any '
                             'files (pair with `--verbose` to see what file '
                             'operations would take place)')
    parser.add_argument('-c', '--config', metavar='CONFIG', type=str,
                        dest='conf_path', default=default_conf_path,
                        help='path to configuration file (*.conf)')
    parser.add_argument('-l', '--library', metavar='LIBRARY', type=str,
                        dest='lib', default=None,
                        help='name of library to use (as specified in config)')
    # Echo subcommand
    echo_help = 'print BibTeX file'
    echo_parser = subparsers.add_parser('echo', description=echo_help,
                                        help=echo_help)
    echo_parser.set_defaults(func=echo)
    # Org subcommand
    org_help = ('automatically create group directories, rename and move '
                'files, and generate new keys from BibTeX fields')
    org_parser = subparsers.add_parser('org', description=org_help,
                                       help=org_help)
    org_parser.set_defaults(func=org)
    # Link subcommand
    link_help = ('link a file to an existing BibTeX entry or create a new '
                 'entry for that file')
    link_parser = subparsers.add_parser('link', description=link_help,
                                        help=link_help)
    link_parser.add_argument('file', metavar='FILE', type=str,
                             help='file to link')
    link_parser.add_argument('-k', '--key', metavar='KEY', type=str,
                             default=None, help='key of entry to link')
    link_parser.set_defaults(func=link)
    # Parse arguments
    args = parser.parse_args()

    # Set logging level
    if args.debug:
        logging_level = logging.DEBUG
        formatter = '[%(asctime)s] %(levelname)s: %(message)s'
    elif args.verbose:
        logging_level = logging.INFO
        formatter = '%(levelname)s: %(message)s'
    else:
        logging_level = logging.WARNING
        formatter = '%(levelname)s: %(message)s'
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
                  conf.getint('config', 'filename_words'),
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
    """Subcommand that parses and prints the BibTeX file to stdout.

    Parameters
    ----------
    lib: Library
        Library object to operate on.
    args: argparse.Namespace
        Arguments to consider.
    """
    lib.open_bib_db()
    for entry in lib.db.values():
        print(entry.to_bib(wrap_width=lib.wrap_width), end='\n\n')


def org(lib, args):
    """Subcommand that organizes library files.

    Specifically, the command
    1. creates missing group directories,
    2. renames files according to their BibTeX metadata,
    3. moves files into their corresponding groups, and
    4. updates the BibTeX entry keys based on their fields.

    Parameters
    ----------
    lib: Library
        Library object to operate on.
    args: argparse.Namespace
        Arguments to consider.
    """
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
    """Subcommand that links a file to a BibTeX entry. Creates a new entry if
    needed.

    Parameters
    ----------
    lib: Library
        Library object to operate on.
    args: argparse.Namespace
        Arguments to consider.
    """
    lib.open_bib_db()
    lib.link_file(args.file, args.key)
    lib.write_bib_file()


class Library:
    """Library class that encapsulates parsed BibTeX file and relevant
    settings from config file."""

    def __init__(self, bibtex_file, storage_path, default_group,
                 filename_words, filename_length, key_length, wrap_width,
                 dry_run):
        """Constructor saves arguments and creates pathlib Path objects form
        string inputs.

        Parameters
        ----------
        bibtex_file: str
            Path to BibTeX file.
        storage_path: str
            Path to folder where linked files are stored.
        default_group: str
            Group where files that have no associated group are stored.
        filename_words: int
            Maximum number of words from title to use in filename.
        filename_length: int
            Maximum number of characters in a filename.
        key_length: int
            Maximum number of characters in a BibTeX key.
        wrap_width: int
            Maximum line length in the BibTeX file. Wraps if longer.
        dry_run: bool
            If True, no file operations are actually done (other than reading
            the BibTeX file).
        """
        # Paths and settings
        self.bibtex_file = pathlib.Path(bibtex_file)
        self.bibtex_bak_file = pathlib.Path(bibtex_file + '.bak')
        self.storage_path = pathlib.Path(storage_path)
        self.default_group = default_group
        self.filename_words = filename_words
        self.filename_length = filename_length
        self.key_length = key_length
        self.wrap_width = wrap_width
        self.dry_run = dry_run
        self.db = None

    def create_missing_groups(self):
        """Goes through BibTeX file and creates groups specified by the
        `group` field.

        If any entries exist without a group, the default group is created
        and they are moved there.
        """
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
                logging.debug(f'Directory `{group_path}` already exists. '
                              'Skipping.')

    def rename_according_to_bib(self):
        """Goes through the BibTeX file and generates a new file name for each
        entry in the format `author_year_title`. Renames the files that don't
        already have the correct filename.

        If any of the `author`, `year`, or `title` BibTeX fields are missing,
        they are skipped. If the new name generated is empty, it is skipped.
        """
        for key, entry in zip(self.db.keys(), self.db.values()):
            # Skip entries with invalid files.
            # Logging takes place inside helper function!
            if not _entry_file_is_valid(key, entry):
                continue
            # Generate the new filename using a helper function.
            filename = _entry_string(entry, self.filename_length,
                                     words_from_title=self.filename_words)
            # If the new filename is empty skip.
            if filename == '':
                logging.warn('Cannot generate new file name for entry with '
                             f'key `{key}`. Skipping.')
                continue
            # Get old path from entry and extract extension.
            old_path = pathlib.Path(entry['file'])
            ext = ''.join(old_path.suffixes)
            # Create new path with new filename (keep extension and location)
            new_path = old_path.parent.joinpath(filename + ext)
            # Double check if path points to a file to avoid accidentally
            # moving directory. `is_file()` is the most important check here.
            if old_path == new_path:
                logging.debug(f'File `{old_path}` does not need to be '
                              'renamed. Skipping.')
            elif new_path.exists():
                logging.warn(f'Cannot rename `{old_path}` to `{new_path}` '
                             'because a file with the same name already '
                             'exists. Skipping.')
            else:
                self.move_file(old_path, new_path)
            entry['file'] = str(new_path)

    def move_according_to_bib(self):
        """Goes through the BibTeX file and determines where each file should
        be located based on its `group` entry. If the file is not where it
        should be, it is moved.
        """
        for key, entry in zip(self.db.keys(), self.db.values()):
            # Skip entries with invalid files.
            # Logging takes place inside helper function.
            if not _entry_file_is_valid(key, entry):
                continue
            # Add default group
            if 'groups' not in entry.keys():
                entry['groups'] = self.default_group
            old_path = pathlib.Path(entry['file'])
            new_path = self.storage_path.joinpath(
                entry['groups']).joinpath(old_path.name)
            # Double check if path points to a file to avoid accidentally
            # moving directory. `is_file()` is the most important check here.
            if old_path == new_path:
                logging.debug(f'File `{old_path}` does not need to be moved. '
                              'Skipping.')
            elif new_path.exists():
                logging.warn(f'Cannot move `{old_path}` to `{new_path}` '
                             'because a file with the same name already '
                             'exists in that location. Skipping.')
            else:
                self.move_file(old_path, new_path)
            entry['file'] = str(new_path)

    def rekey_according_to_bib(self):
        """Goes through the BibTeX file and generates a new key for each entry
        in the format: `author_year_first-word-of-title`. Copies entries into
        a new dictionnary with updated keys.

        Handles duplicates by appending `_dup` to the keys.
        """
        new_db = collections.OrderedDict()
        for key, entry in zip(self.db.keys(), self.db.values()):
            # Use helper to generate a new key
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
            # Need to update the key in the entry and in the dict.
            # It's probably enough to update it in the entry but I'm playing
            # it safe.
            entry.key = new_key
            new_db[new_key] = entry
        self.db = new_db

    def link_file(self, file, key=None):
        """Updates the `file` field in a BibTeX entry. Creates a new entry if 
        no key is specified.

        Parameters
        ----------
        file: str
            Path to file to be linked.
        key: str
            Key of entry to be linked. If `None`, new entry is created with
            filename as key.
        """
        # Read path and set default key
        file_path = pathlib.Path(file)
        if key is None:
            key = file_path.stem
        # Check validity of PDF path, then link if valid.
        if not file_path.exists():
            logging.warning(f'{file_path} does not exist. Not linking.')
        elif not file_path.is_file():
            logging.warning(f'{file_path} is not a file. Not linking.')
        else:
            if key.lower() in self.db:
                self.db[key.lower()]['file'] = str(file_path.resolve())
            else:
                self.db[key.lower()] = biblib.bib.Entry(
                    [('file', str(file_path.resolve()))], key=key.lower(),
                    typ='misc')

    def open_bib_db(self):
        """Opens and reads contents of BibTeX file."""
        logging.info(f'Opening `{self.bibtex_file}`.')
        with open(self.bibtex_file, 'r') as bib:
            self.db = biblib.bib.Parser().parse(bib).get_entries()

    def write_bib_file(self):
        """Writes BibTeX dictionary to file.

        If dry_run is specified, skips file operations.
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

    def move_file(self, old_file, new_file):
        """Moves files but refuses to move directories. Also used for renaming.

        If dry_run is specified, skips file operations.
        """
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
    """Check the validity of a `file` field of an entry.

    Ensures that
    1. the entry has a `file` field,
    2. the `file` field is nonempty,
    3. the file pointed to exists, and
    4. the file pointed to is a file, not a directory.

    Returns
    -------
    bool:
        True if the file is valid by the above definitions. False otherwise.
    """
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
    """Return string with format author_year_title. Used for filenames and
    BibTeX keys.

    If any of the `author`, `year`, or `title` fields are empty or not present,
    they are skipped.

    Parameters
    ----------
    entry: biblib.bib.Entry
        Entry to generate string from.
    max_length: int
        Maximum number of characters in the string
    words_from_title: int
        Maximum number of words to use from title. If `None`, uses whole title.
        For filenames, `None` is used. For BibTeX keys, `1` is used.

    Returns
    -------
    str:
        String with format `author_year_title` based on entry.
    """
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
    """Clean up a string.

    Specifically, cleaning up a string entails
    1. making it lowercase,
    2. replacing spaces with underscores, and
    3. removing any characters that are not lowercase letters, numbers, or
       underscores.

    Parameters
    ----------
    s: str
        String to clean up.

    Returns
    -------
    str:
        Cleaned up string according to above definition.
    """
    valid = string.ascii_lowercase + string.digits + '_'
    s_nospace = s.lower().replace(' ', '_')
    s_clean = ''.join(char for char in s_nospace if char in valid)
    return s_clean
