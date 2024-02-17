"""Reference management tools for BibTeX."""

import configparser
import logging
import os
import pathlib
import shutil
import string
from typing import Optional

import bibtexparser
import click


class Library:
    """BibTeX library."""

    dry_run_prefix = '(Dry run)'

    def __init__(
        self,
        bibtex_file: pathlib.Path,
        storage_path: pathlib.Path,
        default_group: str,
        filename_words: int,
        filename_length: int,
        key_length: int,
        wrap_width: int,
        dry_run: bool,
    ) -> None:
        """Instantiate ``Library``.

        Parameters
        ----------
        bibtex_file : pathlib.Path
            Path to BibTeX file.
        storage_path : pathlib.Path
            Path to folder where added files are stored.
        default_group : str
            Group where files that have no associated group are stored.
        filename_words : int
            Maximum number of words from title to use in filename.
        filename_length : int
            Maximum number of characters in a filename.
        key_length : int
            Maximum number of characters in a BibTeX key.
        wrap_width : int
            Maximum line length in the BibTeX file. Wraps if longer.
        dry_run : bool
            If True, no file operations are actually done (other than reading
            the BibTeX file).
        """
        # Paths and settings
        self.bibtex_file = pathlib.Path(bibtex_file)
        self.storage_path = pathlib.Path(storage_path)
        self.default_group = default_group
        self.filename_words = filename_words
        self.filename_length = filename_length
        self.key_length = key_length
        self.wrap_width = wrap_width
        self.dry_run = dry_run
        self._db = None

    @property
    def bibtex_bak_file(self) -> pathlib.Path:
        """Backup file for BibTeX library."""
        return pathlib.Path(str(self.bibtex_file) + '.bak')

    def open(self):
        """Open BibTeX file."""
        if self._db is None:
            logging.info(f'Opening `{self.bibtex_file}`.')
            self._db = bibtexparser.parse_file(
                self.bibtex_file,
                append_middleware=[
                    bibtexparser.middlewares.SeparateCoAuthors(),
                    bibtexparser.middlewares.SplitNameParts(),
                ],
            )
        else:
            logging.info(f'File `{self.bibtex_file}` already open.')

    def print(self):
        """Print BibTeX file."""
        self._check_open()
        bib_str = bibtexparser.write_string(self._db)
        print(bib_str)

    def create_missing_groups(self):
        """Create groups specified by the `group` field.

        If any entries exist without a group, the default group is created
        and they are moved there.
        """
        for entry in self._db.entries:
            # If group doesn't exist, set it to the default
            if 'groups' in entry:
                group_path = self.storage_path.joinpath(entry['groups'])
            else:
                group_path = self.storage_path.joinpath(self.default_group)
            # If folder does not already exist, create it.
            if not group_path.exists():
                if self.dry_run:
                    logging.info(
                        f'{self.dry_run_prefix} Creating `{group_path}`.')
                else:
                    logging.info(f'Creating `{group_path}`.')
                    group_path.mkdir()
            else:
                logging.debug(
                    f'Directory `{group_path}` already exists. Skipping.')

    def rename_according_to_bib(self):
        """Generate a new file name for each entry.

        File name format is `author_year_title`. Renames the files that don't
        already have the correct filename. If any of the `author`, `year`, or
        `title` BibTeX fields are missing, they are skipped. If the new name
        generated is empty, it is skipped.
        """
        for entry in self._db.entries:
            # Skip entries with invalid files.
            # Logging takes place inside helper function!
            if not self._entry_file_is_valid(entry):
                continue
            # Generate the new filename using a helper function.
            filename = self._entry_string(
                entry,
                self.filename_length,
                words_from_title=self.filename_words,
            )
            # If the new filename is empty skip.
            if filename == '':
                logging.warn('Cannot generate new file name for entry with '
                             f'key `{entry.key}`. Skipping.')
                continue
            # Get old path from entry and extract extension.
            old_path = pathlib.Path(entry['file'])
            ext = _get_extension(old_path)
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
                self._move_file(old_path, new_path)
            entry['file'] = str(new_path)

    def move_according_to_bib(self):
        """Move files to group specified in BibTeX file."""
        for entry in self._db.entries:
            # Skip entries with invalid files.
            # Logging takes place inside helper function.
            if not self._entry_file_is_valid(entry):
                continue
            # Add default group
            if 'groups' not in entry:
                entry['groups'] = self.default_group
            old_path = pathlib.Path(entry['file'])
            new_path = self.storage_path.joinpath(entry['groups']).joinpath(
                old_path.name)
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
                self._move_file(old_path, new_path)
            entry['file'] = str(new_path)

    def rekey_according_to_bib(self):
        """Generate a new key for each entry in the BibTeX file.

        Format is `author_year_first-word-of-title`.
        Handles duplicates by appending `_dup` to the keys.
        """
        new_db = bibtexparser.Library()
        for entry in self._db.entries:
            # Use helper to generate a new key
            new_key = self._entry_string(
                entry,
                self.key_length,
                words_from_title=1,
            )
            # If new key is empty, don't change it
            if new_key == '':
                logging.warn('Cannot generate new key for entry with key '
                             f'`{entry.key}`. Skipping.')
                new_key = entry.key
            # If there's a duplicate, change the name
            if new_key != entry.key:
                while new_key in self._db.entries_dict.keys():
                    logging.warn(f'Two entires share the key `{entry.key}`. '
                                 'Appending `_dup` to second entry.')
                    new_key += '_dup'
            else:
                logging.debug(f'Key {new_key} not changed.')
            entry.key = new_key
            new_db.add(entry)
        self._db = new_db

    def write_bib_file(self):
        """Write BibTeX dictionary to file.

        If dry_run is specified, skips file operations.
        """
        if self.dry_run:
            logging.info(
                f'{self.dry_run_prefix} Deleting `{self.bibtex_bak_file}`.')
            logging.info(
                f'{self.dry_run_prefix} Moving `{self.bibtex_file}` to '
                f'`{self.bibtex_bak_file}`.')
            logging.info(
                f'{self.dry_run_prefix} Writing `{self.bibtex_file}`.')
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
            bibtexparser.write_file(
                str(self.bibtex_file.resolve()),
                self._db,
                append_middleware=[
                    bibtexparser.middlewares.MergeNameParts(),
                    bibtexparser.middlewares.MergeCoAuthors(),
                ],
            )

    def _check_open(self):
        """Raise error if BibTeX file is not open."""
        if self._db is None:
            raise RuntimeError('Must call `open()` to open BibTeX file.')

    def _move_file(self, old_file, new_file):
        """Move files but refuse to move directories.

        Also used for renaming. If dry_run is specified, skips file operations.
        """
        if self.dry_run:
            logging.info(
                f'{self.dry_run_prefix} Moving `{old_file}` to `{new_file}`.')
        elif not old_file.exists():
            logging.warning(f'{old_file} does not exist. Not moving.')
        elif not old_file.is_file():
            logging.warning(f'{old_file} is not a file. Not moving.')
        else:
            logging.info(f'Moving `{old_file}` to `{new_file}`.')
            shutil.move(old_file, new_file)

    @staticmethod
    def _entry_file_is_valid(entry: bibtexparser.model.Entry) -> bool:
        """Check the validity of a `file` field of an entry.

        Ensures that
        1. the entry has a `file` field,
        2. the `file` field is nonempty,
        3. the file pointed to exists, and
        4. the file pointed to is a file, not a directory.

        Parameters
        ----------
        entry : bibtexparser.model.Entry
            Entry to check.

        Returns
        -------
        bool:
            True if the file is valid by the above definitions.
        """
        if 'file' not in entry:
            logging.warn(f'No file in entry with key `{entry.key}`. Skipping.')
            return False
        if entry['file'] == '':
            logging.warn(f'File field in entry with key `{entry.key}` is '
                         'empty. Skipping.')
            return False
        if not pathlib.Path(entry['file']).exists():
            logging.warn(f"File `{entry['file']}` in entry with key "
                         f"`{entry.key}` does not exist. Skipping.")
            return False
        if not pathlib.Path(entry['file']).is_file():
            logging.warn(f"File `{entry['file']}` in entry with key "
                         f"`{entry.key}` is not a file. Skipping.")
            return False
        return True

    @staticmethod
    def _entry_string(
        entry: bibtexparser.model.Entry,
        max_length: int,
        words_from_title: Optional[int] = None,
    ) -> str:
        """Return string with format author_year_title.

        Used for filenames and BibTeX keys. If any of the `author`, `year`, or
        `title` fields are empty or not present, they are skipped.

        Parameters
        ----------
        entry: bibtexparser.model.Entry
            Entry to generate string from.
        max_length: int
            Maximum number of characters in the string
        words_from_title: int
            Maximum number of words to use from title. If `None`, uses whole
            title. For filenames, `None` is used. For BibTeX keys, `1` is used.

        Returns
        -------
        str:
            String with format `author_year_title` based on entry.
        """
        string_components = []
        if 'author' in entry:
            # Last name of first author
            string_components.append(_clean_string(entry['author'][0].last[0]))
        if 'year' in entry:
            string_components.append(_clean_string(entry['year']))
        if 'title' in entry:
            if words_from_title is None:
                # Take all of title
                string_components.append(_clean_string(entry['title']))
            else:
                # Take up to `words_from_title` words from title
                string_components.append(
                    _clean_string('_'.join(
                        entry['title'].split(' ')[:words_from_title])))
        entry_string = '_'.join(string_components)[:max_length]
        return entry_string


@click.group()
@click.option('--verbose', is_flag=True, help='')
@click.option('--debug', is_flag=True, help='')
@click.option('--dry-run', is_flag=True, help='')
@click.option(
    '-c',
    '--config',
    type=click.Path(exists=True, dir_okay=False, path_type=pathlib.Path),
    help='',
)
@click.option('-L', '--library', type=str, help='')
@click.pass_context
def cli(ctx, verbose, debug, dry_run, config, library):
    """Manage BibTeX references."""
    # Set logging level
    if debug:
        logging_level = logging.DEBUG
        formatter = '[%(asctime)s] %(levelname)s: %(message)s'
    elif verbose:
        logging_level = logging.INFO
        formatter = '%(levelname)s: %(message)s'
    else:
        logging_level = logging.WARNING
        formatter = '%(levelname)s: %(message)s'
    logging.basicConfig(format=formatter, level=logging_level)
    # Parse config
    conf = configparser.ConfigParser()
    conf.read(_get_default_config_path() if config is None else config)
    if library is None:
        selected_lib = conf['config']['default_library']
    else:
        selected_lib = library
    # Create library
    ctx.obj = Library(
        conf[selected_lib]['bibtex_file'],
        conf[selected_lib]['storage_path'],
        conf[selected_lib]['default_group'],
        conf.getint('config', 'filename_words'),
        conf.getint('config', 'filename_length'),
        conf.getint('config', 'key_length'),
        conf.getint('config', 'wrap_width'),
        dry_run,
    )


@cli.command()
@click.pass_obj
def echo(library):
    """Parse and print BibTeX file to stdout."""
    library.open()
    library.print()


@cli.command()
@click.pass_obj
def org(library):
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
    conf: configparser.ConfigParser
        Parsed config file.
    """
    library.open()
    library.create_missing_groups()
    library.rename_according_to_bib()
    library.move_according_to_bib()
    library.rekey_according_to_bib()
    library.write_bib_file()


def _get_default_config_path() -> Optional[pathlib.Path]:
    """Get default config path.

    Returns
    -------
    Optional[pathlib.Path]
        Default configuration path if it can be determined, otherwise ``None``.
    """
    config_file = 'bibmgr/bibmgr.conf'
    if os.name == 'posix':
        # Use XDG default if specified
        xdg_config_home_raw = os.environ.get('XDG_CONFIG_HOME')
        if xdg_config_home_raw is None:
            # Use ``~/.config`` if not specified
            home = os.environ.get('HOME')
            if home is not None:
                xdg_config_home = pathlib.Path(home, '.config')
            else:
                return None
        else:
            xdg_config_home = pathlib.Path(xdg_config_home_raw)
        default_conf_path = xdg_config_home.joinpath(config_file)
    else:
        # Use ``%LOCALAPPDATA%`` if specified
        localappdata = os.environ.get('LOCALAPPDATA')
        if localappdata is not None:
            default_conf_path = pathlib.Path(localappdata, config_file)
        else:
            return None
    return default_conf_path


def _clean_string(s: str) -> str:
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


def _get_extension(path: pathlib.Path) -> str:
    """Get the extension of a path.

    Assumes all extensions except ``.tar.gz`` and ``.tar.bz2`` are single
    extensions.

    Parameters
    ----------
    path: pathlib.Path
        Path to file.

    Returns
    -------
    str:
        File extension.
    """
    known_double_extensions = ['.tar.gz', '.tar.bz2']
    # If extension is not a known double extension, take last part only.
    extensions = ''.join(path.suffixes)
    if extensions in known_double_extensions:
        ext = extensions
    else:
        ext = path.suffixes[-1]
    return ext


if __name__ == '__main__':
    cli()
