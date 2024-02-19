"""PDF parsing."""

import logging
import pathlib
import re
import string
from typing import Dict, Optional

import pdfminer.high_level
import pdfminer.layout
import pdfminer.pdfdocument
import pdfminer.pdfparser

# TODO check metadata and name

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

old_arxiv_name_re = r'.*(\d\d\d\d\d\d\d).*'
new_arxiv_name_re = r'.*(\d\d\d\d\.\d\d\d\d\d?).*'
old_arxiv_text_re = r'.*\/(\d\d\d\d\d\d\d).*'
new_arxiv_text_re = r'.*arXiv\:(\d\d\d\d\.\d\d\d\d\d?).*'

# https://www.crossref.org/blog/dois-and-matching-regular-expressions/
doi_re = r'.*(10.\d{4,9}\/[-._;()/:A-Z0-9]+).*'


# TODO
def parse_pdf(path: pathlib.Path) -> Dict[str, Optional[str]]:
    """Parse PDF."""
    pass


def _parse_filename(path: pathlib.Path) -> Dict[str, Optional[str]]:
    """Construct a search query from a PDF file.

    Parameters
    ----------
    file : pathlib.Path
        File name.

    Returns
    -------
    str :
        Search query.
    """
    match_new = re.match(new_arxiv_name_re, path.stem)
    match_old = re.match(old_arxiv_name_re, path.stem)
    if match_new is not None:
        id = match_new.group(1)
    elif match_old is not None:
        id = match_old.group(1)
    else:
        id = None
    metadata = {
        'title': None,
        'author': None,
        'arxiv_id': id,
        'doi': None,
    }
    return metadata


def _parse_pdf_metadata(path: pathlib.Path) -> Dict[str, Optional[str]]:
    """Construct a search query from a PDF file.

    Parameters
    ----------
    file : pathlib.Path
        File name.

    Returns
    -------
    str :
        Search query.
    """
    metadata: Dict[str, Optional[str]] = {
        'title': None,
        'author': None,
        'arxiv_id': None,
        'doi': None,
    }

    with open(path, 'rb') as f:
        parser = pdfminer.pdfparser.PDFParser(f)
        doc = pdfminer.pdfdocument.PDFDocument(parser)
        # Look for arXiv link in annotations of first page
        first_page = next(pdfminer.pdfpage.PDFPage.create_pages(doc))
        if first_page.annots:
            for annotation in first_page.annots:
                url_b = annotation.resolve().get('A', {}).get('URI', None)
                if url_b is not None:
                    url = url_b.decode('utf-8', errors='ignore')
                    match_new = re.match(new_arxiv_name_re, url)
                    match_old = re.match(old_arxiv_name_re, url)
                    if match_new is not None:
                        id = match_new.group(1)
                    elif match_old is not None:
                        id = match_old.group(1)
                    else:
                        id = None
                    if (id is not None) and (metadata['arxiv_id'] is None):
                        metadata['arxiv_id'] = id
        parser.close()
    # Look for DOI or arXiv ID in metadata
    title = doc.info[0]['Title'].decode('utf-8', errors='ignore')
    if title != '':
        metadata['title'] = title
    author = doc.info[0]['Author'].decode('utf-8', errors='ignore')
    if author != '':
        metadta['author'] = author
    for key, value_b in doc.info[0].items():
        # Match arXiv ID
        value = value_b.decode('utf-8', errors='ignore')
        match_new_arxiv_text = re.match(new_arxiv_text_re, value)
        match_old_arxiv_text = re.match(old_arxiv_text_re, value)
        if match_new_arxiv_text is not None:
            id = match_new_arxiv_text.group(1)
        elif match_old_arxiv_text is not None:
            id = match_old_arxiv_text.group(1)
        else:
            id = None
        if (id is not None) and (metadata['arxiv_id'] is None):
            metadata['arxiv_id'] = id
        # Match DOI
        match_doi = re.match(doi_re, value, flags=re.IGNORECASE)
        if (match_doi is not None) and (metadata['doi'] is None):
            metadata['doi'] = match_doi.group(1)
    return metadata


# TODO
def _parse_pdf_text(path: pathlib.Path) -> str:
    """Construct a search query from a PDF file.

    Parameters
    ----------
    file : pathlib.Path
        File name.

    Returns
    -------
    str :
        Search query.
    """
    max_pages = 2
    metadata: Dict[str, Optional[str]] = {
        'title': None,
        'author': None,
        'arxiv_id': None,
        'doi': None,
    }
    for page in pdfminer.high_level.extract_pages(path, maxpages=max_pages):
        for element in page:
            if isinstance(element, pdfminer.layout.LTTextContainer):
                text = element.get_text()
                # Match arXiv ID
                match_new_arxiv_text = re.match(new_arxiv_text_re, text)
                match_old_arxiv_text = re.match(old_arxiv_text_re, text)
                if match_new_arxiv_text is not None:
                    id = match_new_arxiv_text.group(1)
                elif match_old_arxiv_text is not None:
                    id = match_old_arxiv_text.group(1)
                else:
                    id = None
                if (id is not None) and (metadata['arxiv_id'] is None):
                    metadata['arxiv_id'] = id
                # Match DOI
                match_doi = re.match(doi_re, text, flags=re.IGNORECASE)
                if (match_doi is not None) and (metadata['doi'] is None):
                    metadata['doi'] = match_doi.group(1)
    return metadata


# TODO
def _parse_pdf_text_old(file: pathlib.Path) -> str:
    """Construct a search query from a PDF file.

    Parameters
    ----------
    file : pathlib.Path
        File name.

    Returns
    -------
    str :
        Search query.
    """
    # Extract relevant text chunks and their font sizes
    text_chunks = []
    text_sizes = []
    mp = 2  # TODO
    ml = 4  # TODO
    minw = 2  # TODO
    maxw = 30  # TODO
    maxc = 200  # TODO
    for page_layout in pdfminer.high_level.extract_pages(file, maxpages=mp):
        for element in page_layout:
            if isinstance(element, pdfminer.layout.LTTextContainer):
                text = element.get_text()
                lines = text.count('\n')
                if lines > ml:
                    # If the element has too many lines, it's probably a
                    # paragraph from the main body. Skip it.
                    continue
                else:
                    # Remove all invalid characters
                    valid_chars = (string.ascii_letters + string.digits +
                                   string.punctuation + ' ' + '\n')
                    text_ascii = ''.join(char for char in text
                                         if char in valid_chars)
                    # Replace all groups of whitespace characters with a single
                    # space.
                    text_stripped = re.sub(r'\s+', ' ', text_ascii).strip()
                    # Count the number of words. Skip if there are too many
                    # or too few.
                    words = text_stripped.count(' ') + 1
                    if words < minw:
                        continue
                    if words > maxw:
                        continue
                    # Find size of second character in the string.
                    # Skips the first in case there's a drop cap.
                    first_char = True
                    for text_line in element:
                        if isinstance(text_line, pdfminer.layout.LTTextLine):
                            for character in text_line:
                                if isinstance(character,
                                              pdfminer.layout.LTChar):
                                    char_size = int(character.size)
                                    if not first_char:
                                        break
                                    first_char = False
                            break
                    text_chunks.append(text_stripped)
                    text_sizes.append(char_size)
    # Throw out text boxes with font size under the threshold. Build query.
    # Threshold is current just the max size
    threshold_size = max(text_sizes)
    query = ''
    for chunk, size in zip(text_chunks, text_sizes):
        if size >= threshold_size:
            if len(query + ' ' + chunk) <= maxc:
                query += (' ' + chunk)
    return query.strip()
