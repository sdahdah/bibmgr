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

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

new_arxiv_name_re = r'.*(\d\d\d\d\.\d\d\d\d\d?).*'
old_arxiv_text_re = r'.*arXiv\:(.*\/\d\d\d\d\d\d\d).*'
new_arxiv_text_re = r'.*arXiv\:(\d\d\d\d\.\d\d\d\d\d?).*'

# https://www.crossref.org/blog/dois-and-matching-regular-expressions/
doi_re = r'.*(10.\d{4,9}\/[-._;()/:A-Z0-9]+).*'


class Metadata:
    """PDF metadata."""

    def __init__(
        self,
        title: Optional[str] = None,
        author: Optional[str] = None,
        arxiv_id: Optional[str] = None,
        doi: Optional[str] = None,
    ):
        """Instantiate ``Metadata``."""
        self.title = title
        self.author = author
        self.arxiv_id = arxiv_id
        self.doi = doi

    def __repr__(self):
        """Represent ``Metadata`` as a string."""
        return str({
            'title': self.title,
            'author': self.author,
            'arxiv_id': self.arxiv_id,
            'doi': self.doi,
        })


def parse_pdf(
    path: pathlib.Path,
    max_pages: int,
    max_lines: int,
    min_words: int,
    max_words: int,
    max_chars: int,
) -> Metadata:
    """Parse PDF.

    Parameters
    ----------
    file : pathlib.Path
        File name.

    Returns
    -------
    Metadata :
        PDF metadata.
    """
    filename = _parse_filename(path)
    pdf_metadata = _parse_pdf_metadata(path)
    pdf_text = _parse_pdf_text(
        path,
        max_pages=max_pages,
        max_lines=max_lines,
        min_words=min_words,
        max_words=max_words,
        max_chars=max_chars,
    )
    metadata = Metadata()
    # Set title
    if pdf_metadata.title:
        metadata.title = pdf_metadata.title
    elif pdf_text.title:
        metadata.title = pdf_text.title
    elif filename.title:
        metadata.title = filename.title
    # Set author
    if pdf_metadata.author:
        metadata.author = pdf_metadata.author
    elif pdf_text.author:
        metadata.author = pdf_text.author
    elif filename.author:
        metadata.author = filename.author
    # Set arXiv ID
    if pdf_text.arxiv_id:
        metadata.arxiv_id = pdf_text.arxiv_id
    elif filename.arxiv_id:
        metadata.arxiv_id = filename.arxiv_id
    elif pdf_metadata.arxiv_id:
        metadata.arxiv_id = pdf_metadata.arxiv_id
    # Set DOI
    if pdf_metadata.doi:
        metadata.doi = pdf_metadata.doi
    elif pdf_text.doi:
        metadata.doi = pdf_text.doi
    elif filename.doi:
        metadata.doi = filename.doi
    return metadata


def _parse_filename(path: pathlib.Path) -> Metadata:
    """Get metadata from PDF file name.

    Parameters
    ----------
    file : pathlib.Path
        File name.

    Returns
    -------
    Metadata :
        PDF metadata.
    """
    match_new = re.match(new_arxiv_name_re, path.stem)
    if match_new is not None:
        id = match_new.group(1)
    else:
        id = None
    metadata = Metadata(arxiv_id=id)
    return metadata


def _parse_pdf_metadata(path: pathlib.Path) -> Metadata:
    """Get metadata from PDF metadata.

    Parameters
    ----------
    file : pathlib.Path
        File name.

    Returns
    -------
    Metadata :
        PDF metadata.
    """
    metadata = Metadata()
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
                    if match_new is not None:
                        id = match_new.group(1)
                    else:
                        id = None
                    if (id is not None) and (metadata.arxiv_id is None):
                        metadata.arxiv_id = id
        parser.close()
    # Look for DOI or arXiv ID in metadata
    title = doc.info[0]['Title'].decode('utf-8', errors='ignore')
    if title != '':
        metadata.title = title
    author = doc.info[0]['Author'].decode('utf-8', errors='ignore')
    if author != '':
        metadata.author = author
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
        if (id is not None) and (metadata.arxiv_id is None):
            metadata.arxiv_id = id
        # Match DOI
        match_doi = re.match(doi_re, value, flags=re.IGNORECASE)
        if (match_doi is not None) and (metadata.doi is None):
            metadata.doi = match_doi.group(1)
    return metadata


def _parse_pdf_text(
    path: pathlib.Path,
    max_pages: int,
    max_lines: int,
    min_words: int,
    max_words: int,
    max_chars: int,
) -> Metadata:
    """Get metadata from PDF text.

    Parameters
    ----------
    file : pathlib.Path
        File name.
    max_pages : int
        Maximum number of pages to parse.
    max_lines : int
        Maximum number of lines in a text box.
    min_words : int
        Minimum number of words in a text box.
    max_words : int
        Maximum number of words in a text box.
    max_chars : int
        Maximum number of characters in the title.

    Returns
    -------
    Metadata :
        PDF metadata.
    """
    text_chunks = []
    text_sizes = []
    metadata = Metadata()
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
                if (id is not None) and (metadata.arxiv_id is None):
                    metadata.arxiv_id = id
                # Match DOI
                match_doi = re.match(doi_re, text, flags=re.IGNORECASE)
                if (match_doi is not None) and (metadata.doi is None):
                    metadata.doi = match_doi.group(1)
                # Look for title
                lines = text.count('\n')
                if lines > max_lines:
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
                    if words < min_words:
                        continue
                    if words > max_words:
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
            if len(query + ' ' + chunk) <= max_chars:
                query += (' ' + chunk)
    if metadata.title is None:
        metadata.title = query.strip()
    return metadata
