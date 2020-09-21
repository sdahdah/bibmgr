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
                        dest='config_path', default='', help='path to '
                        'default configuration file (*.cfg)')
    parser.add_argument('lib', metavar='LIBRARY', type=str, help='')
    # Echo subcommand
    echo_parser = subparsers.add_parser('echo')
    echo_parser.set_defaults(func=echo)
    # Org subcommand
    org_parser = subparsers.add_parser('org')
    org_parser.set_defaults(func=org)

    # Parse arguments
    args = parser.parse_args()

    # Load and parse config files
    cfg = configparser.ConfigParser()
    cfg.read(args.config_path)

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
