"""PDF parsing and lookup."""

import logging
from typing import List, Optional

import arxiv
import bibtexparser
import habanero

from . import utilities

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class CrossrefResult():
    """Crossref result."""

    def __init__(self, raw):
        """Instantiate ``CrossrefResult``."""
        self.raw = raw
        self._bibtex = None

    @property
    def title(self) -> str:
        """Get title."""
        return self.raw.get('title', [''])[0]

    @property
    def author(self) -> str:
        """Get author."""
        author_names = []
        for entry in self.raw.get('author', []):
            name_parts = []
            given = entry.get('given', '')
            family = entry.get('family', '')
            if given != '':
                name_parts.append(given)
            if family != '':
                name_parts.append(family)
            author_names.append(' '.join(name_parts))
        author_string = ' and '.join(author_names)
        return author_string

    @property
    def doi(self) -> str:
        """Get DOI."""
        return self.raw.get('DOI', '')

    def get_entry(self, force_update=False) -> bibtexparser.model.Entry:
        """Get BibTeX information from Crossref."""
        if (self._bibtex is None) or force_update:
            if (self.doi is None) or (self.doi == ''):
                given = self.author.split(' ')[0]
                title = self.title.split(' ')[0]
                key = utilities.clean_string_for_key(given + '_' + title)
                self._bibtex = bibtexparser.model.Entry(
                    entry_type='misc',
                    key=key,
                    fields=[
                        bibtexparser.model.Field(
                            key='title',
                            value=self.title,
                        ),
                        bibtexparser.model.Field(
                            key='author',
                            value=self.author,
                        ),
                    ],
                )
            else:
                result = habanero.cn.content_negotiation(
                    ids=self.doi,
                    format='bibentry',
                )
                self._bibtex = bibtexparser.parse_string(result).entries[0]
        return self._bibtex


class ArxivResult():
    """arXiv result."""

    def __init__(self, raw):
        """Instantiate ``ArxivResult``."""
        self.raw = raw
        self._bibtex = None

    @property
    def title(self) -> str:
        """Get title."""
        return '' if self.raw.title is None else self.raw.title

    @property
    def author(self) -> str:
        """Get author."""
        if self.raw.authors is None:
            author_string = ''
        else:
            author_names = [str(a) for a in self.raw.authors]
            author_string = ' and '.join(author_names)
        return author_string

    @property
    def doi(self) -> str:
        """Get DOI."""
        return '' if self.raw.doi is None else self.raw.doi

    def get_entry(self, force_update=False) -> bibtexparser.model.Entry:
        """Get BibTeX information from Crossref."""
        if (self._bibtex is None) or force_update:
            if (self.doi is None) or (self.doi == ''):
                given = self.author.split(' ')[0]
                title = self.title.split(' ')[0]
                key = utilities.clean_string_for_key(given + '_' + title)
                id = self.raw.entry_id.split('/')[-1]
                cat = self.raw.primary_category
                if (cat is None) or (cat == ''):
                    jt = f'{{\\tt arXiv:{id}}}'
                else:
                    jt = f'{{\\tt arXiv:{id}[{cat}]}}'
                self._bibtex = bibtexparser.model.Entry(
                    entry_type='article',
                    key=key,
                    fields=[
                        bibtexparser.model.Field(
                            key='title',
                            value=self.title,
                        ),
                        bibtexparser.model.Field(
                            key='author',
                            value=self.author,
                        ),
                        bibtexparser.model.Field(
                            key='year',
                            value=self.raw.published.year,
                        ),
                        bibtexparser.model.Field(
                            key='journaltitle',
                            value=jt,
                        ),
                    ],
                )
            else:
                result = habanero.cn.content_negotiation(
                    ids=self.doi,
                    format='bibentry',
                )
                self._bibtex = bibtexparser.parse_string(result).entries[0]
        return self._bibtex


def query_crossref(
    query: str,
    limit: int,
    mailto: Optional[str] = None,
) -> List[CrossrefResult]:
    """Query Crossref."""
    crossref = habanero.Crossref(mailto=mailto)
    results = crossref.works(
        query=query,
        limit=limit,
    )
    crossref_results = [CrossrefResult(r) for r in results['message']['items']]
    return crossref_results


def query_crossref_doi(
    doi: str,
    mailto: Optional[str] = None,
) -> List[CrossrefResult]:
    """Query Crossref by DOI."""
    crossref = habanero.Crossref(mailto=mailto)
    results = crossref.works(ids=doi, warn=True)
    if results is None:
        return []
    else:
        crossref_results = [CrossrefResult(results['message'])]
        return crossref_results


def query_arxiv(query: str, limit: int) -> List[ArxivResult]:
    """Query arXiv."""
    client = arxiv.Client()
    search = arxiv.Search(
        query=query,
        max_results=limit,
    )
    try:
        results = client.results(search)
        arxiv_results = [ArxivResult(r) for r in results]
    except arxiv.ArxivError:
        log.warn('Error searching arXiv.')
        arxiv_results = []
    return arxiv_results


def query_arxiv_id(id: str) -> List[ArxivResult]:
    """Query arXiv by ID."""
    client = arxiv.Client()
    search = arxiv.Search(id_list=[id])
    try:
        results = client.results(search)
        arxiv_results = [ArxivResult(r) for r in results]
    except arxiv.ArxivError:
        log.warn('Error searching arXiv.')
        arxiv_results = []
    return arxiv_results
