"""PDF parsing and lookup."""

import abc
import logging
from typing import Optional, Sequence

import arxiv
import bibtexparser
import habanero

from . import utilities

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class SearchResult(object, metaclass=abc.ABCMeta):
    """Search result."""

    def __init__(self):
        """Instantiate ``SearchResult``."""
        super().__init__()

    @property
    @abc.abstractmethod
    def title(self) -> str:
        """Get title."""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def author(self) -> str:
        """Get author."""
        raise NotImplementedError()

    @property
    @abc.abstractmethod
    def doi(self) -> str:
        """Get DOI."""
        raise NotImplementedError()

    @abc.abstractmethod
    def get_entry(self, force_update=False) -> bibtexparser.model.Entry:
        """Get BibTeX information from Crossref."""
        raise NotImplementedError()

    def __repr__(self) -> str:
        """Represent ``SearchResult`` as a string."""
        out = []
        if self.title:
            out.append(self.title)
        if self.author:
            out.append(self.author)
        if self.doi:
            out.append(self.doi)
        return '\n'.join(out)


class CrossrefResult(SearchResult):
    """Crossref result."""

    def __init__(self, raw):
        """Instantiate ``CrossrefResult``."""
        super().__init__()
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
                entry_str = f'''@misc{{{key},
                title={{{self.title}}},
                author={{{self.author}}},
                }}
                '''
                self._bibtex = bibtexparser.parse_string(
                    entry_str,
                    append_middleware=[
                        bibtexparser.middlewares.SeparateCoAuthors(),
                        bibtexparser.middlewares.SplitNameParts(),
                    ],
                ).entries[0]
            else:
                result = habanero.cn.content_negotiation(
                    ids=self.doi,
                    format='bibentry',
                )
                self._bibtex = bibtexparser.parse_string(
                    result,
                    append_middleware=[
                        bibtexparser.middlewares.SeparateCoAuthors(),
                        bibtexparser.middlewares.SplitNameParts(),
                    ],
                ).entries[0]
        return self._bibtex


class ArxivResult(SearchResult):
    """arXiv result."""

    def __init__(self, raw):
        """Instantiate ``ArxivResult``."""
        super().__init__()
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
                entry_str = f'''@misc{{{key},
                title={{{self.title}}},
                author={{{self.author}}},
                year={{{self.raw.published.year}}},
                journaltitle={{{jt}}},
                }}
                '''
                self._bibtex = bibtexparser.parse_string(
                    entry_str,
                    append_middleware=[
                        bibtexparser.middlewares.SeparateCoAuthors(),
                        bibtexparser.middlewares.SplitNameParts(),
                    ],
                ).entries[0]
            else:
                result = habanero.cn.content_negotiation(
                    ids=self.doi,
                    format='bibentry',
                )
                self._bibtex = bibtexparser.parse_string(
                    result,
                    append_middleware=[
                        bibtexparser.middlewares.SeparateCoAuthors(),
                        bibtexparser.middlewares.SplitNameParts(),
                    ],
                ).entries[0]
        return self._bibtex


def query_crossref(
    query: str,
    limit: int,
    mailto: Optional[str] = None,
) -> Sequence[CrossrefResult]:
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
) -> Sequence[CrossrefResult]:
    """Query Crossref by DOI."""
    crossref = habanero.Crossref(mailto=mailto)
    results = crossref.works(ids=doi, warn=True)
    if results is None:
        return []
    else:
        crossref_results = [CrossrefResult(results['message'])]
        return crossref_results


def query_arxiv(query: str, limit: int) -> Sequence[ArxivResult]:
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


def query_arxiv_id(id: str) -> Sequence[ArxivResult]:
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


def rank_results(
    results: Sequence[SearchResult],
    query: str,
) -> Sequence[SearchResult]:
    """Rank search results."""
    # Find number of words from query in title
    common_words = []
    query_words = utilities.clean_string_for_query(query).split(' ')
    for res in results:
        count = 0
        title_words = utilities.clean_string_for_query(res.title).split(' ')
        author_words = utilities.clean_string_for_query(
            res.author).split(' and ')
        for word in query_words:
            if (word in title_words) or (word in author_words):
                count += 1
        common_words.append(count)
    # Sort by number of words from query in title
    results_sorted = [
        res for _, res in sorted(
            zip(common_words, results), key=lambda pair: pair[0], reverse=True)
    ]
    return results_sorted
