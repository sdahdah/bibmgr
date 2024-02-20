"""Reference management tools for BibTeX."""

import configparser
import logging
import os
import pathlib
import subprocess
from typing import Optional, Sequence

import click

from . import library_model, parse, search, utilities

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


@click.group()
@click.option('--verbose', is_flag=True, help='Print detailed output.')
@click.option('--debug', is_flag=True, help='Print debug information.')
@click.option(
    '--dry-run',
    is_flag=True,
    help='Run command without moving or writing to any files.',
)
@click.option(
    '-c',
    '--config',
    type=click.Path(exists=True, dir_okay=False, path_type=pathlib.Path),
    help='Specify configuration file.',
)
@click.option(
    '-L',
    '--library',
    type=str,
    help='Select library, as specified in config.',
)
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
    conf['DEFAULT'] = {
        'default_library':
        '',
        'filename_words':
        4,
        'filename_length':
        100,
        'key_length':
        40,
        'editor':
        '',
        'field_order': ('title, author, month, year, booktitle, journaltitle, '
                        'eventtitle, journal, publisher, location, series, '
                        'volume, number, pages, numpages, issn, doi, url, '
                        'groups, keywords, comment, file'),
        'mandatory_fields': ('title, author, year, groups, keywords, comment, '
                             'file'),
        'max_query_results':
        10,
        'polite_pool_email':
        '',
        'max_pages':
        2,
        'max_lines':
        4,
        'min_words':
        2,
        'max_words':
        30,
        'max_chars':
        200,
        'bibtex_file':
        '',
        'storage_path':
        '',
        'default_group':
        'unfiled',
    }
    conf.read(_get_default_config_path() if config is None else config)
    if library is None:
        selected_lib = conf.get('bibmgr', 'default_library')
    else:
        selected_lib = library
    # Create library
    ctx.obj = {
        'library':
        library_model.Library(
            conf.get(selected_lib, 'bibtex_file'),
            conf.get(selected_lib, 'storage_path'),
            conf.get(selected_lib, 'default_group'),
            conf.getint('bibmgr', 'filename_words'),
            conf.getint('bibmgr', 'filename_length'),
            conf.getint('bibmgr', 'key_length'),
            conf.get('bibmgr', 'field_order').split(', '),
            conf.get('bibmgr', 'mandatory_fields').split(', '),
            dry_run,
        ),
        'config':
        conf,
    }


@cli.command()
@click.pass_obj
def echo(obj):
    """Print BibTeX library."""
    library = obj['library']
    library.open()
    library.print()


@cli.command()
@click.pass_obj
def org(obj):
    """Organize BibTeX library and linked files."""
    library = obj['library']
    library.open()
    library.organize()
    library.write_bib_file()


@cli.command()
@click.pass_obj
def edit(obj):
    """Open BibTeX library in text editor."""
    library = obj['library']
    conf_editor = obj['config'].get('bibmgr', 'editor')
    env_editor = os.environ.get('EDITOR')
    editor = env_editor if conf_editor is None else conf_editor
    subprocess.call([editor, library.bibtex_file])


@cli.command()
@click.argument(
    'files',
    type=click.Path(exists=True, dir_okay=False, path_type=pathlib.Path),
    nargs=-1,
)
@click.option(
    '-k',
    '--key',
    type=str,
    default=None,
    help='Destination key for BibTeX entry.',
)
@click.option(
    '-q',
    '--query',
    type=str,
    default=None,
    help='Manually specified query. Only supported when adding one file.',
)
@click.option(
    '-s',
    '--skip-query',
    is_flag=True,
    help='Skip online query and BibTeX reorganization.',
)
@click.option(
    '-i',
    '--interactive',
    is_flag=True,
    help='Run an interactive query.',
)
@click.pass_obj
def add(obj, files, key, query, skip_query, interactive):
    """Add linked files to BibTeX library."""
    if query and (len(files) > 1):
        log.info('Query unsupported when adding multiple files.')
        return
    library = obj['library']
    config = obj['config']
    library.open()
    for file in files:
        new_key = library.add_file(file, key)
        if skip_query:
            continue
        if query:
            entries = _query_string(
                query,
                limit=config.getint('bibmgr', 'max_query_results'),
                mailto=config.get('bibmgr', 'polite_pool_email'),
            )
        else:
            # Get metadata
            metadata = parse.parse_pdf(
                file,
                max_pages=config.getint('parsing', 'max_pages'),
                max_lines=config.getint('parsing', 'max_lines'),
                min_words=config.getint('parsing', 'min_words'),
                max_words=config.getint('parsing', 'max_words'),
                max_chars=config.getint('parsing', 'max_chars'),
            )
            if interactive:
                print('Metadata')
                print('--------')
                print(metadata)
                print()
            # Query online based on metadata
            entries = _query_file(
                metadata,
                limit=config.getint('bibmgr', 'max_query_results'),
                mailto=config.get('bibmgr', 'polite_pool_email'),
            )
            if interactive:
                print('Results')
                print('-------')
                for (k, result) in enumerate(entries):
                    result_str = str(result).replace('\n', '\n    ')
                    print(f'[{k}] {result_str}')
                sel = click.prompt('Selection', default=0)
        if entries:
            if (len(entries) > 1) and (sel < len(entries)) and interactive:
                library.update_entry(new_key, entries[sel].get_entry())
            else:
                library.update_entry(new_key, entries[0].get_entry())
    if not skip_query:
        library.organize()
    library.write_bib_file()


def _query_file(
    metadata: parse.Metadata,
    limit: int = 10,
    mailto: Optional[str] = None,
) -> Sequence[search.SearchResult]:
    """Query by file metadata."""
    if not mailto:
        log.warn('`mailto` not specified, not in Crossref polite pool.')
    # Check metadata
    if not metadata:
        return []
    # Search by DOI first
    entries: Sequence[search.SearchResult]
    if metadata.doi:
        entries = search.query_crossref_doi(metadata.doi, mailto=mailto)
        if entries:
            return entries
    # Search by arXiv ID if no DOI
    if metadata.arxiv_id:
        entries = search.query_arxiv_id(metadata.arxiv_id)
        if entries:
            return entries
    # Fall back on text query
    query_title = utilities.clean_string_for_query(metadata.title)
    query_author = utilities.clean_string_for_query(metadata.author)
    query = query_title + query_author
    ranked_entries = _query_string(query, limit=limit, mailto=mailto)
    return ranked_entries


def _query_string(
    query: str,
    limit: int = 10,
    mailto: Optional[str] = None,
) -> Sequence[search.SearchResult]:
    """Query by file."""
    if not mailto:
        log.warn('`mailto` not specified, not in Crossref polite pool.')
    entries_crossref = search.query_crossref(query, limit=limit, mailto=mailto)
    entries_arxiv = search.query_arxiv(query, limit=limit)
    entries = list(entries_crossref) + list(entries_arxiv)
    ranked_entries = search.rank_results(entries, query)
    return ranked_entries


def _get_default_config_path() -> Optional[pathlib.Path]:
    """Get default config path."""
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


if __name__ == '__main__':
    cli()
