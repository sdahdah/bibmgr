import argparse
import sys
import pathlib
import biblib.bib
import configparser


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
        assert False  # TODO

    # Run subcommand
    args.func(args, cfg)


def echo(args, cfg):
    lib_path = pathlib.Path(cfg[args.lib]['path'])
    bib_path = lib_path.joinpath(f'{args.lib}.bib')

    with open(bib_path, 'r') as bib:
        db = biblib.bib.Parser().parse(bib, log_fp=sys.stderr).get_entries()

    for entry in db.values():
        print(entry.to_bib())


def org(args, cfg):
    lib_path = pathlib.Path(cfg[args.lib]['path'])
    bib_path = lib_path.joinpath(f'{args.lib}.bib')

    with open(bib_path, 'r') as bib:
        db = biblib.bib.Parser().parse(bib, log_fp=sys.stderr).get_entries()

    for entry in db.values():
        group_path = lib_path.joinpath(entry['groups'])
        try:
            group_path.mkdir()
            print(f'Created {group_path}')
        except FileExistsError:
            pass
        # TODO Move files as needed


def link(args, cfg):
    lib_path = pathlib.Path(cfg[args.lib]['path'])
    bib_path = lib_path.joinpath(f'{args.lib}.bib')
    bak_path = lib_path.joinpath(f'{args.lib}.bib.bak')

    with open(bib_path, 'r') as bib:
        db = biblib.bib.Parser().parse(bib, log_fp=sys.stderr).get_entries()

    pdf_path = pathlib.Path(args.pdf)
    if pdf_path.exists():
        pass
    else:
        assert False  # TODO

    db[args.key]['file'] = str(pdf_path.resolve().relative_to(lib_path))

    bib_path.rename(bak_path)
    with open(bib_path, 'a') as bib:
        for entry in db.values():
            bib.write(entry.to_bib())
