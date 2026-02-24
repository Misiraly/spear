"""
Fuzzy song-title search using tokenized Levenshtein distance.

Algorithm (adapted from the original pandas-based implementation):
  1. Tokenize both the query and the candidate title into words, then also
     generate concatenations of neighbouring word pairs so that "darkside"
     matches "dark side" etc.
  2. For every (query_token, title_token) pair, compute the Levenshtein
     distance.  If a query token is an exact substring of the title the pair
     scores 1 (very close match).
  3. Collect the N smallest distances and use that sorted tuple as the sort key
     for the whole song list.  Shorter distance lists rank higher; Python's
     tuple comparison does the right thing.
  4. Return the top ``limit`` songs.

No pandas required — operates directly on the list-of-dicts produced by
song_metadata.get_songs_alphabetically() and friends.
"""

import re
from typing import Optional

from rapidfuzz.distance import Levenshtein

# ---------------------------------------------------------------------------
# Character normalisation map (Hungarian diacritics → ASCII equivalents)
# ---------------------------------------------------------------------------
_REPLACE_CHAR: dict[str, str] = {
    "á": "a",
    "é": "e",
    "í": "i",
    "ó": "o",
    "ö": "o",
    "ő": "o",
    "ú": "u",
    "ü": "u",
    "ű": "u",
}

_PUNCT_SPACE = re.compile(r"[;:\-\+\.\?!,\[\]\(\)\{\}<>\*\~\|=_]")
_PUNCT_DROP = re.compile(r"""[\'\"\"\/\\#\$%&@\^`]""")


def _normalize(text: str) -> str:
    """Lowercase, strip punctuation, and normalise diacritics."""
    text = text.lower()
    text = _PUNCT_SPACE.sub(" ", text)
    text = _PUNCT_DROP.sub("", text)
    for char, replacement in _REPLACE_CHAR.items():
        text = text.replace(char, replacement)
    return text


def tokenize_neighbor(text: str) -> list[str]:
    """Tokenize *text* and append neighbouring-word concatenations.

    Example::

        "what are yoű)dö^ing?"
        → ["what", "are", "youdoing", "whatare", "areyoudoing"]

    The neighbour pairs give the search tolerance for compound words and
    missing spaces (e.g. "darkside" finding "Dark Side of the Moon").
    """
    tokens = _normalize(text).split()
    tokens = [t for t in tokens if t]
    neighbor_tokens = [tokens[i] + tokens[i + 1] for i in range(len(tokens) - 1)]
    return tokens + neighbor_tokens


def _token_distance(query: str, title: str, depth: int = 6) -> list[int]:
    """Return the *depth* smallest Levenshtein distances between all
    (query_token, title_token) pairs.

    An exact substring match scores 1 (better than most near-matches but
    worse than an identical token pair which scores 0).
    """
    query_tokens = tokenize_neighbor(query)
    title_lower = title.lower()
    title_tokens = tokenize_neighbor(title)

    distances: list[int] = []
    for qt in query_tokens:
        if qt in title_lower:
            distances.append(1)  # substring hit — strong signal
        for tt in title_tokens:
            distances.append(Levenshtein.distance(qt, tt))

    distances.sort()
    return distances[:depth]


def fuzzy_search(
    query: str,
    songs: list[dict],
    limit: int = 10,
    depth: int = 6,
) -> list[dict]:
    """Rank *songs* by fuzzy title similarity to *query* and return the top results.

    Args:
        query:  The user's search string (raw, un-normalised).
        songs:  List of song dicts (must contain at least ``"title"`` and
                ``"uid"``).  Typically the alphabetical list from
                ``song_metadata.get_songs_alphabetically()``.
        limit:  Maximum number of results to return.
        depth:  Number of best token-distances to include in the sort key.
                Higher values consider more context; 6 is a good default.

    Returns:
        A list of song dicts, best match first, length ≤ *limit*.
    """
    if not query or not songs:
        return []

    scored = sorted(
        songs,
        key=lambda s: _token_distance(query, s.get("title", ""), depth),
    )
    return scored[:limit]
