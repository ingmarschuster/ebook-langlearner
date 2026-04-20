"""Lemmatization backed by :mod:`simplemma` with an in-process LRU cache.

simplemma is lightweight and supports 50+ European languages without requiring
per-language model downloads. Results are cached per ``(word, lang)`` because
lemmatization is pure and the annotator calls it once per word occurrence.
"""

from __future__ import annotations

from functools import lru_cache

import simplemma


@lru_cache(maxsize=200_000)
def lemmatize(word: str, lang: str) -> str:
    """Return the dictionary form (lemma) of ``word`` in ``lang``.

    On any error from :mod:`simplemma` (including unsupported language) the
    function falls back to the lowercased input so that the caller can still
    attempt a frequency lookup.

    Args:
        word: The surface form to lemmatize.
        lang: A language code supported by :mod:`simplemma`.

    Returns:
        The lemma. Falls back to ``word.lower()`` if lemmatization raises.
    """
    try:
        return simplemma.lemmatize(word, lang=lang)
    except (ValueError, KeyError):
        return word.lower()
