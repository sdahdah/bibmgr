"""BibTeX library manipulation."""

import logging
import pathlib
import shutil
from typing import List, Optional

import bibtexparser

from . import utilities

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class Library:
    """BibTeX library."""

    def __init__(
        self,
        bibtex_file: pathlib.Path,
        storage_path: pathlib.Path,
        default_group: str,
        filename_words: int,
        filename_length: int,
        key_length: int,
        field_order: List[str],
        mandatory_fields: List[str],
        dry_run: bool,
    ) -> None:
        """Instantiate ``Library``."""
        # Paths and settings
        self.bibtex_file = pathlib.Path(bibtex_file)
        self.storage_path = pathlib.Path(storage_path)
        self.default_group = default_group
        self.filename_words = filename_words
        self.filename_length = filename_length
        self.key_length = key_length
        self.field_order = field_order
        self.mandatory_fields = mandatory_fields
        self.dry_run = dry_run
        # Set up database
        self._db: Optional[bibtexparser.Library] = None
        # Set up BibTeX format
        self._bibtex_format = bibtexparser.BibtexFormat()
        self._bibtex_format.indent = '    '
        self._bibtex_format.block_separator = '\n'
        self._bibtex_format.trailing_comma = True

    @property
    def bibtex_bak_file(self) -> pathlib.Path:
        """Backup file for BibTeX library."""
        return pathlib.Path(str(self.bibtex_file) + '.bak')

    def open(self) -> None:
        """Open BibTeX file."""
        if self._db is None:
            log.info(f'Opening `{self.bibtex_file}`.')
            self._db = bibtexparser.parse_file(
                str(self.bibtex_file.resolve()),
                append_middleware=[
                    bibtexparser.middlewares.SeparateCoAuthors(),
                    bibtexparser.middlewares.SplitNameParts(),
                ],
            )
            if len(self._db.failed_blocks) > 0:
                failed_blocks = [
                    block.start_line for block in self._db.failed_blocks
                ]
                log.warning(
                    f'Failed to parse blocks on lines: {failed_blocks}')
        else:
            log.info(f'File `{self.bibtex_file}` already open.')

    def print(self) -> None:
        """Print BibTeX file."""
        db = self._get_db()
        bib_str = bibtexparser.write_string(
            db,
            prepend_middleware=[
                bibtexparser.middlewares.MergeNameParts(),
                bibtexparser.middlewares.MergeCoAuthors(),
                bibtexparser.middlewares.SortFieldsCustomMiddleware(
                    order=tuple(self.field_order)),
            ],
            bibtex_format=self._bibtex_format,
        )
        print(bib_str)

    def create_missing_groups(self) -> None:
        """Create groups specified by the `group` field.

        If any entries exist without a group, the default group is created
        and they are moved there.
        """
        db = self._get_db()
        for entry in db.entries:
            # If group doesn't exist, set it to the default
            if ('groups' in entry) and (entry['groups'] != ''):
                group_path = self.storage_path.joinpath(entry['groups'])
            else:
                group_path = self.storage_path.joinpath(self.default_group)
            # If folder does not already exist, create it.
            if not group_path.exists():
                if self.dry_run:
                    self._dry_run_msg(f'Creating `{group_path}`.')
                else:
                    log.info(f'Creating `{group_path}`.')
                    group_path.mkdir()
            else:
                log.debug(
                    f'Directory `{group_path}` already exists. Skipping.')

    def create_missing_fields(self) -> None:
        """Create missing fields."""
        db = self._get_db()
        for entry in db.entries:
            for field in self.mandatory_fields:
                if field not in entry:
                    if field == 'author':
                        entry[field] = []
                    elif field == 'groups':
                        entry[field] = self.default_group
                    else:
                        entry[field] = ''

    def rename_according_to_bib(self) -> None:
        """Generate a new file name for each entry.

        File name format is `author_year_title`. Renames the files that don't
        already have the correct filename. If any of the `author`, `year`, or
        `title` BibTeX fields are missing, they are skipped. If the new name
        generated is empty, it is skipped.
        """
        db = self._get_db()
        for entry in db.entries:
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
            if (filename is None) or (filename == ''):
                log.warn('Cannot generate new file name for entry with '
                         f'key `{entry.key}`. Skipping.')
                continue
            # Get old path from entry and extract extension.
            old_path = pathlib.Path(entry['file'])
            ext = utilities.get_extension(old_path)
            # Create new path with new filename (keep extension and location)
            new_path = old_path.parent.joinpath(filename + ext)
            # Double check if path points to a file to avoid accidentally
            # moving directory. `is_file()` is the most important check here.
            if old_path == new_path:
                log.debug(f'File `{old_path}` does not need to be '
                          'renamed. Skipping.')
            elif new_path.exists():
                log.warn(f'Cannot rename `{old_path}` to `{new_path}` '
                         'because a file with the same name already '
                         'exists. Skipping.')
            else:
                self._move_file(old_path, new_path)
            entry['file'] = str(new_path)

    def move_according_to_bib(self) -> None:
        """Move files to group specified in BibTeX file."""
        db = self._get_db()
        for entry in db.entries:
            # Skip entries with invalid files.
            # Logging takes place inside helper function.
            if not self._entry_file_is_valid(entry):
                continue
            # Add default group
            if 'groups' not in entry:
                entry['groups'] = self.default_group
            elif entry['groups'] == '':
                entry['groups'] = self.default_group
            old_path = pathlib.Path(entry['file'])
            new_path = self.storage_path.joinpath(
                entry['groups'],
                old_path.name,
            )
            # Double check if path points to a file to avoid accidentally
            # moving directory. `is_file()` is the most important check here.
            if old_path == new_path:
                log.debug(f'File `{old_path}` does not need to be moved. '
                          'Skipping.')
            elif new_path.exists():
                log.warn(f'Cannot move `{old_path}` to `{new_path}` '
                         'because a file with the same name already '
                         'exists in that location. Skipping.')
            else:
                self._move_file(old_path, new_path)
            entry['file'] = str(new_path)

    def rekey_according_to_bib(self) -> None:
        """Generate a new key for each entry in the BibTeX file.

        Format is `author_year_first-word-of-title`.
        Handles duplicates by appending `_dup` to the keys.
        """
        db = self._get_db()
        new_db = bibtexparser.Library()
        for entry in db.entries:
            # Use helper to generate a new key
            new_key = self._entry_string(
                entry,
                self.key_length,
                words_from_title=1,
            )
            # If new key is empty, don't change it
            if (new_key is None) or (new_key == ''):
                log.warn('Cannot generate new key for entry with key '
                         f'`{entry.key}`. Skipping.')
                new_key = entry.key
            # If there's a duplicate, change the name
            if new_key != entry.key:
                while new_key in db.entries_dict.keys():
                    log.warn(f'Two entires share the key `{entry.key}`. '
                             'Appending `_dup` to second entry.')
                    new_key += '_dup'
            else:
                log.debug(f'Key {new_key} not changed.')
            entry.key = new_key
            new_db.add(entry)
        self._db = new_db

    def add_file(self, file: str, key: Optional[str] = None) -> None:
        """Update the `file` field in a BibTeX entry.

        Creates a new entry if no key is specified.
        """
        db = self._get_db()
        # Read path and set default key
        file_path = pathlib.Path(file)
        if key is None:
            key = utilities.clean_string_for_key(file_path.stem)
        key = key.lower()
        # Check validity of PDF path, then link if valid.
        if not file_path.exists():
            log.warning(f'{file_path} does not exist. Not adding.')
        elif not file_path.is_file():
            log.warning(f'{file_path} is not a file. Not adding.')
        else:
            if key in db.entries_dict.keys():
                db.entries_dict[key]['file'] = str(file_path.resolve())
            else:
                entry = bibtexparser.model.Entry(
                    entry_type='misc',
                    key=key,
                    fields=[
                        bibtexparser.model.Field(
                            key='file',
                            value=str(file_path.resolve()),
                        )
                    ],
                )
                db.add(entry)

    def write_bib_file(self) -> None:
        """Write BibTeX dictionary to file.

        If dry_run is specified, skips file operations.
        """
        db = self._get_db()
        if self.dry_run:
            self._dry_run_msg(f'Deleting `{self.bibtex_bak_file}`.')
            self._dry_run_msg(
                f'Moving `{self.bibtex_file}` to `{self.bibtex_bak_file}`.')
            self._dry_run_msg(f'Writing `{self.bibtex_file}`.')
        else:
            # Delete .bak file if it exists
            log.info(f'Deleting `{self.bibtex_bak_file}`.')
            self.bibtex_bak_file.unlink(missing_ok=True)
            # Rename .bib file to .bib.bak
            log.info(f'Moving `{self.bibtex_file}` to '
                     f'`{self.bibtex_bak_file}`.')
            if self.bibtex_file.exists():
                self.bibtex_file.rename(self.bibtex_bak_file)
            # Write new .bib file
            log.info(f'Writing `{self.bibtex_file}`.')
            bibtexparser.write_file(
                str(self.bibtex_file.resolve()),
                db,
                append_middleware=[
                    bibtexparser.middlewares.MergeNameParts(),
                    bibtexparser.middlewares.MergeCoAuthors(),
                    bibtexparser.middlewares.SortFieldsCustomMiddleware(
                        order=tuple(self.field_order)),
                ],
                bibtex_format=self._bibtex_format,
            )

    def _get_db(self) -> bibtexparser.Library:
        """Raise error if BibTeX file is not open."""
        if self._db is None:
            raise RuntimeError('Must call `open()` to open BibTeX file.')
        return self._db

    def _move_file(
        self,
        old_file: pathlib.Path,
        new_file: pathlib.Path,
    ) -> None:
        """Move files but refuse to move directories.

        Also used for renaming. If dry_run is specified, skips file operations.
        """
        if self.dry_run:
            self._dry_run_msg(f'Moving `{old_file}` to `{new_file}`.')
        elif not old_file.exists():
            log.warning(f'{old_file} does not exist. Not moving.')
        elif not old_file.is_file():
            log.warning(f'{old_file} is not a file. Not moving.')
        else:
            log.info(f'Moving `{old_file}` to `{new_file}`.')
            shutil.move(old_file, new_file)

    @staticmethod
    def _dry_run_msg(s: str) -> None:
        """Print dry run info message."""
        log.info('(Dry run) ' + s)

    @staticmethod
    def _entry_file_is_valid(entry: bibtexparser.model.Entry) -> bool:
        """Check the validity of a `file` field of an entry.

        Ensures that the entry has a `file` field, the `file` field is
        nonempty, the file pointed to exists, and the file pointed to is
        a file, not a directory.
        """
        if 'file' not in entry:
            log.warn(f'No file in entry with key `{entry.key}`. Skipping.')
            return False
        if entry['file'] == '':
            log.warn(f'File field in entry with key `{entry.key}` is '
                     'empty. Skipping.')
            return False
        if not pathlib.Path(entry['file']).exists():
            log.warn(f"File `{entry['file']}` in entry with key "
                     f"`{entry.key}` does not exist. Skipping.")
            return False
        if not pathlib.Path(entry['file']).is_file():
            log.warn(f"File `{entry['file']}` in entry with key "
                     f"`{entry.key}` is not a file. Skipping.")
            return False
        return True

    @staticmethod
    def _entry_string(
        entry: bibtexparser.model.Entry,
        max_length: int,
        words_from_title: Optional[int] = None,
    ) -> Optional[str]:
        """Return string with format author_year_title.

        Used for filenames and BibTeX keys. If any of the `author`, `year`, or
        `title` fields are empty or not present, they are skipped.
        """
        string_components = []
        if ('author' in entry) and (len(entry['author']) > 0):
            # Last name of first author
            last_name = entry['author'][0].last[0]
            string_components.append(utilities.clean_string_for_key(last_name))
        if ('year' in entry) and (entry['year'] != ''):
            string_components.append(
                utilities.clean_string_for_key(entry['year']))
        if ('title' in entry) and (entry['title'] != ''):
            if words_from_title is None:
                # Take all of title
                string_components.append(
                    utilities.clean_string_for_key(entry['title']))
            else:
                # Take up to `words_from_title` words from title
                string_components.append(
                    utilities.clean_string_for_key('_'.join(
                        entry['title'].split(' ')[:words_from_title])))
        if len(string_components) > 0:
            entry_string = '_'.join(string_components)[:max_length]
        else:
            entry_string = None
        return entry_string
