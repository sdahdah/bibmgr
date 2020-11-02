import argparse
import sys
import pathlib
import biblib.bib
import biblib.algo
import configparser
import string
import shutil


def main():
    parser = argparse.ArgumentParser(description='')
    subparsers = parser.add_subparsers()

    # Shared arguments
    parser.add_argument('-c', '--config', metavar='CONFIG', type=str,
                        dest='cfg_path', default='', help='path to '
                        'default configuration file (*.cfg)')
    parser.add_argument('-l', '--library', metavar='LIBRARY', type=str,
                        dest='lib', default='', help='Name of library to use')
    # Echo subcommand
    echo_parser = subparsers.add_parser('echo')
    echo_parser.set_defaults(func=echo)
    # Org subcommand
    org_parser = subparsers.add_parser('org')
    org_parser.set_defaults(func=org)
    # Link subcommand
    link_parser = subparsers.add_parser('link')
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
        # TODO Get rid of exception
        raise FileNotFoundError(args.cfg_path)

    # TODO make sure config and library are valid before continuing

    # Run subcommand
    args.func(args, cfg)


def echo(args, cfg):
    _, bib_path, _ = _get_paths(args, cfg)
    db = _open_bib_db(bib_path)

    for entry in db.values():
        print(entry.to_bib())


def org(args, cfg):
    lib_path, bib_path, bak_path = _get_paths(args, cfg)
    db = _open_bib_db(bib_path)
    # Create new group folders
    _create_missing_groups(lib_path, db)
    # TODO Rename files according to metadata
    _rename_according_to_bib(lib_path, bib_path, bak_path, db,
                             cfg.getint('config', 'max_file_name_length'))
    # TODO Move files to correct groups
    # Write new bib file


def link(args, cfg):
    lib_path, bib_path, bak_path = _get_paths(args, cfg)
    db = _open_bib_db(bib_path)

    # Make sure desired PDF exists
    pdf_path = pathlib.Path(args.pdf)
    if not pdf_path.exists():
        # TODO Get rid of exception
        raise FileNotFoundError(args.pdf)

    # TODO Update to is_relative_to once 3.9 is a thing
    # Set file field. Ise relative path if the pdf is within the library.
    # Otherwise, use the absolute path.
    try:
        db[args.key.lower()]['file'] = \
            str(pdf_path.resolve().relative_to(lib_path))
    except ValueError:
        db[args.key.lower()]['file'] = \
            str(pdf_path.resolve())

    _write_bib_file(lib_path, bib_path, bak_path, db)

# TODO Move some arg/cmd shenanigans here
# class Library:

#     def __init__(self, lib_path, max_filename_len):
#         self.lib_path = lib_path
#         self.max_filename_len = max_filename_len


def _create_missing_groups(lib_path, db):
    """"""
    for entry in db.values():
        group_path = lib_path.joinpath(entry['groups'])
        try:
            group_path.mkdir()
        except FileExistsError:
            pass  # Folder exists, don't need to do anything


def _rename_according_to_bib(lib_path, bib_path, bak_path, db,
                             max_file_name_length):
    """"""
    for key, entry in zip(db.keys(), db.values()):
        # Take last name of first author
        name = _clean_string(
            biblib.algo.parse_names(entry['author'])[0].last)
        year = _clean_string(entry['year'])
        title = _clean_string(entry['title'])
        filename = (name + '_' + year + '_' + title)[:max_file_name_length]
        if filename == '':
            # TODO Get rid of exception
            raise RuntimeError(f"New file name for key '{key}' is empty, "
                               f"cannot rename.")
        pdf_path = lib_path.joinpath(entry['file'])
        ext = ''.join(pdf_path.suffixes)
        new_path = pdf_path.parent.joinpath(filename + ext)
        shutil.move(pdf_path, new_path)
        try:
            entry['file'] = str(new_path.resolve().relative_to(lib_path))
        except ValueError:
            entry['file'] = str(new_path.resolve())
    _write_bib_file(lib_path, bib_path, bak_path, db)


def _clean_string(s):
    """"""
    valid = string.ascii_lowercase + string.digits + '_'
    s_nospace = s.lower().replace(' ', '_')
    s_clean = ''.join(char for char in s_nospace if char in valid)
    return s_clean


def _move_according_to_bib(db):
    """"""
    pass


def _get_paths(args, cfg):
    """Extracts library and BibTeX file paths from arguments and configuration
    file.

    Parameters
    ----------
    args : argparse.Namespace
        Command line arguments (from argparse).
    cfg : configparser.ConfigParser
        Parsed configuration file (from configparser).

    Returns
    -------
    tuple
        Library base path, BibTeX file path, and BibTeX file backup paths,
        all of type pathlib.Path (from pathlib).
    """
    lib_path = pathlib.Path(cfg[args.lib]['path'])
    bib_path = lib_path.joinpath(f'{args.lib}.bib')
    bak_path = lib_path.joinpath(f'{args.lib}.bib.bak')
    return lib_path, bib_path, bak_path


def _open_bib_db(bib_path):
    """Opens BibTeX file and returns biblib dictionary.

    Parameters
    ----------
    bib_path : pathlib.Path
        Path of BibTeX file.

    Returns
    -------
    collections.OrderedDict
        BibTeX dictionary (from biblib).
    """
    with open(bib_path, 'r') as bib:
        db = biblib.bib.Parser().parse(bib, log_fp=sys.stderr).get_entries()
    return db


def _write_bib_file(lib_path, bib_path, bak_path, db):
    """Writes BibTeX dictionary to file.

    Parameters
    ----------
    lib_path : pathlib.Path
        Base path of library.
    bib_path : pathlib.Path
        Path of BibTeX file.
    bak_path : pathlib.Path
        Path of BibTeX backup file.
    db : collections.OrderedDict
        BibTeX dictionary to write (from biblib).
    """
    # Delete .bak file if it exists
    bak_path.unlink(missing_ok=True)
    # Rename .bib file to .bib.bak
    if bib_path.exists():
        bib_path.rename(bak_path)
    # Write new .bib file
    with open(bib_path, 'a') as bib:
        for entry in db.values():
            bib.write(entry.to_bib())
