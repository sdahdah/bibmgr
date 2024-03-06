# bibmgr

CLI reference management tools for BibTeX.

Can fetch BibTeX entries from Crossref and arXiv using [pdflu](https://github.com/sdahdah/pdflu).

Very much a work-in-progress right now (even more so than `pdflu`).

## Usage

Top-level command:

```
Usage: bibmgr [OPTIONS] COMMAND [ARGS]...

  Manage BibTeX references.

Options:
  --verbose           Print detailed output.
  --debug             Print debug information.
  --dry-run           Run command without moving or writing to any files.
  -c, --config FILE   Specify configuration file.
  -L, --library TEXT  Select library, as specified in config.
  --help              Show this message and exit.

Commands:
  add   Add linked files to BibTeX library.
  echo  Print BibTeX library.
  edit  Open BibTeX library in text editor.
  org   Organize BibTeX library and linked files.
```

Add a PDF to the library:

```
Usage: bibmgr add [OPTIONS] [FILES]...

  Add linked files to BibTeX library.

Options:
  -K, --key TEXT       Destination key for BibTeX entry.
  -q, --query TEXT     Manually specified query. Only supported when adding
                       one file.
  -k, --keywords TEXT  Keyword to apply to all added files
  -s, --skip-query     Skip online query and BibTeX reorganization.
  -i, --interactive    Run an interactive query.
  --help               Show this message and exit.
```

Print the library:

```
Usage: bibmgr echo [OPTIONS]

  Print BibTeX library.

Options:
  --help  Show this message and exit.
```

Edit the BibTeX file manually:

```
Usage: bibmgr edit [OPTIONS]

  Open BibTeX library in text editor.

Options:
  --help  Show this message and exit.
```

Reformat the BibTeX file and move/rename the linked PDFs.

```
Usage: bibmgr org [OPTIONS]

  Organize BibTeX library and linked files.

Options:
  --help  Show this message and exit.
```

## Configuration

Place the following file in`~/.config/bibmgr/bibmgr.conf`:

```ini
[bibmgr]
# Default library to manipulate
default_library = library
# Maximum number of words from title to put in file name
filename_words = 4
# Max number of characters in file name
filename_length = 100
# Max number of characters in BibTeX key
key_length = 40
# Your favourite editor for `bibmgr edit`
editor = nvim
# Order of BibTeX fields
field_order = title, author, month, year, booktitle, journaltitle, eventtitle, journal, publisher, location, series, volume, number, pages, numpages, issn, doi, url, groups, keywords, comment, file
# Mandatory BibTeX fields, will be filled blank if not specified
mandatory_fields = title, author, year, groups, keywords, comment, file
# Maximum number of query results to fetch (per API)
max_query_results = 10
# Put an email here to gain access to the Crossref API's polite pool, which
# gives better performance. For more info, see
# https://github.com/CrossRef/rest-api-doc#good-manners--more-reliable-service
polite_pool_email = you@email.com

[parsing]
# Maximum number of pages to parse
max_pages = 2
# Maximum number of lines for text box to be parsed
max_lines = 4
# Minimum number of words for text box to be parsed
min_words = 2
# Maximum number of words for text box to be parsed
max_words = 30
# Maximum number of characters in a query
max_chars = 200

# Can define as many libraries as you want
[library]
bibtex_file = /home/.../library.bib
storage_path = /home/.../library
default_group = unfiled

# vi: ft=conf
```
