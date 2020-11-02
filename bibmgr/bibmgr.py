import os
import argparse
import sys
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
        default_cfg_path = xdg_config_home.joinpath('bibmgr/bibmgr.cfg')
    else:
        # If on Windows, must specify manually for now
        default_cfg_path = ''

    parser = argparse.ArgumentParser(description='')
    subparsers = parser.add_subparsers()

    # Shared arguments
    parser.add_argument('-c', '--config', metavar='CONFIG', type=str,
                        dest='cfg_path', default=default_cfg_path,
                        help='path to default configuration file (*.cfg)')
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
    link_parser.add_argument('key', metavar='KEY', type=str, help='')
    link_parser.add_argument('pdf', metavar='PDF', type=str, help='')
    link_parser.set_defaults(func=link)

    # Parse arguments
    args = parser.parse_args()

    # Load and parse config files
    if pathlib.Path(args.cfg_path).exists():
        cfg = configparser.ConfigParser()
        cfg.read(args.cfg_path)
    else:
        raise FileNotFoundError(args.cfg_path)

    # Choose library if none is specified
    if args.lib is None:
        for section in cfg.keys():
            if 'path' in cfg[section].keys():
                selected_lib = section
                break
    else:
        selected_lib = args.lib

    lib = Library(cfg[selected_lib]['path'],
                  cfg.getint('config', 'filename_len'),
                  cfg.getint('config', 'key_len'))

    # Run subcommand
    args.func(lib, args)


def echo(lib, args):
    lib.open_bib_db()
    for entry in lib.db.values():
        print(entry.to_bib(), end='\n\n')


def org(lib, args):
    lib.open_bib_db()
    # Create new group folders
    lib.create_missing_groups()
    # Rename files according to metadata
    lib.rename_according_to_bib()
    # Move files to correct groups
    lib.move_according_to_bib()
    # Update keys according to metadata
    # lib.rekey_according_to_bib()  # TODO Re-enable
    # Write new bib file
    lib.write_bib_file()


def link(lib, args):
    lib.open_bib_db()
    lib.link_file(args.pdf, args.key)
    lib.write_bib_file()


class Library:

    def __init__(self, lib_path, filename_len, key_len):
        self.lib_path = pathlib.Path(lib_path)
        self.bib_path = self.lib_path.joinpath(f'{self.lib_path.stem}.bib')
        self.bak_path = self.lib_path.joinpath(f'{self.lib_path.stem}.bib.bak')
        self.filename_len = filename_len
        self.key_len = key_len
        self.db = None

    def create_missing_groups(self):
        for entry in self.db.values():
            group_path = self.lib_path.joinpath(entry['groups'])
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
            filename = (name + '_' + year + '_' + title)[:self.filename_len]
            if filename == '':
                raise RuntimeError(f"New file name for key '{key}' is empty, "
                                   f"cannot rename.")
            pdf_path = \
                self.lib_path.joinpath(self.read_relative_path(entry['file']))
            ext = ''.join(pdf_path.suffixes)
            new_path = pdf_path.parent.joinpath(filename + ext)
            shutil.move(pdf_path, new_path)
            entry['file'] = str(self.format_relative_path(new_path))

    def move_according_to_bib(self):
        for key, entry in zip(self.db.keys(), self.db.values()):
            pdf_path = self.read_relative_path(entry['file'])
            new_path = \
                self.lib_path.joinpath(entry['groups']).joinpath(pdf_path.name)
            shutil.move(pdf_path, new_path)
            entry['file'] = str(self.format_relative_path(new_path))

    # def rekey_according_to_bib(self):
    #     new_db = collections.OrderedDict()
    #     for key, entry in zip(self.db.keys(), self.db.values()):
    #         # Take last name of first author
    #         name = _clean_string(
    #             biblib.algo.parse_names(entry['author'])[0].last)
    #         year = _clean_string(entry['year'])
    #         title = _clean_string(entry['title'].split(' ')[0])
    #         new_key = (name + '_' + year + '_' + title)[:self.key_len]
    #         # TODO Fine-tune this behaviour
    #         if new_key == '':
    #             continue
    #         # TODO Fine-tune this behaviour too
    #         while new_key in new_db.keys():
    #             new_key += '_dup'
    #         entry.key = new_key  # TODO ???
    #         new_db[new_key] = entry
    #     self.db = new_db

    def link_file(self, key, pdf):
        # Make sure desired PDF exists
        pdf_path = pathlib.Path(pdf)
        if not pdf_path.exists():
            raise FileNotFoundError(pdf)

        self.db[key.lower()]['file'] = str(self.format_relative_path(pdf_path))

    def open_bib_db(self):
        """Opens and reads contents of BibTeX file.

        Parameters
        ----------
        bib_path : pathlib.Path
            Path of BibTeX file.
        """
        with open(self.bib_path, 'r') as bib:
            self.db = biblib.bib.Parser().parse(bib).get_entries()

    def write_bib_file(self):
        """Writes BibTeX dictionary to file.
        """
        # Delete .bak file if it exists
        self.bak_path.unlink(missing_ok=True)
        # Rename .bib file to .bib.bak
        if self.bib_path.exists():
            self.bib_path.rename(self.bak_path)
        # Write new .bib file
        with open(self.bib_path, 'a') as bib:
            for entry in self.db.values():
                bib.write(entry.to_bib())
                bib.write('\n\n')

    def format_relative_path(self, path):
        # TODO Update to is_relative_to once 3.9 is a thing
        try:
            return path.resolve().relative_to(self.lib_path)
        except ValueError:
            return path.resolve()

    def read_relative_path(self, path):
        try:
            return pathlib.Path(path).resolve(strict=True)
        except FileNotFoundError:
            return self.lib_path.joinpath(path)


def _clean_string(s):
    valid = string.ascii_lowercase + string.digits + '_'
    s_nospace = s.lower().replace(' ', '_')
    s_clean = ''.join(char for char in s_nospace if char in valid)
    return s_clean
