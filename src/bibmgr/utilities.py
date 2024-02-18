"""Shared utilities."""

import pathlib
import string


def clean_string(s: str) -> str:
    """Clean up a string.

    Makes the string lowercase, replaces spaces with underscores, and removes
    characters that are not lowercase letters, numbers, or underscores.
    """
    valid = string.ascii_lowercase + string.digits + '_'
    s_nospace = s.lower().replace(' ', '_')
    s_clean = ''.join(char for char in s_nospace if char in valid)
    return s_clean


def get_extension(path: pathlib.Path) -> str:
    """Get the extension of a path.

    Assumes all extensions except ``.tar.gz`` and ``.tar.bz2`` are single
    extensions.
    """
    known_double_extensions = ['.tar.gz', '.tar.bz2']
    # If extension is not a known double extension, take last part only.
    extensions = ''.join(path.suffixes)
    if extensions in known_double_extensions:
        ext = extensions
    else:
        ext = path.suffixes[-1]
    return ext
