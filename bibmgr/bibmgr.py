import argparse
import sys
import biblib.bib


def main():
    # TODO This is copy-pasted from the biblib examples
    arg_parser = argparse.ArgumentParser(description='Parse .bib database(s)'
                                         ' and print basic fields as text')
    arg_parser.add_argument('bib', nargs='+', help='.bib file(s) to process',
                            type=open)
    args = arg_parser.parse_args()

    db = biblib.bib.Parser().parse(args.bib, log_fp=sys.stderr).get_entries()

    breakpoint()

    for ent in db.values():
        print(ent.to_bib())
        print()
