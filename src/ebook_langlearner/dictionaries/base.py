"""Dictionary interface and candidate selection.

All backends implement :class:`Dictionary` and return *raw* candidate
translations for a lookup key; selection (first N unique candidates in
dictionary order) is done uniformly by :func:`select_candidates`.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class LookupKey:
    """Arguments for a dictionary lookup.

    Attributes:
        lemma: The dictionary-form word to look up (not the inflected form).
        source_lang: ISO 639-1 code of the source language.
        target_lang: ISO 639-1 code of the target (translation) language.
    """

    lemma: str
    source_lang: str
    target_lang: str


class Dictionary(ABC):
    """A translation lookup backend.

    Backends should return raw candidate translations in the order the source
    provides them. Deduplication and truncation are applied uniformly by
    :func:`select_candidates`.
    """

    @abstractmethod
    def candidates(self, key: LookupKey) -> list[str]:
        """Return all candidate translations for ``key``.

        Args:
            key: The lookup key.

        Returns:
            A list of candidate translation strings (possibly empty).
        """
        raise NotImplementedError


def select_candidates(candidates: list[str], limit: int = 2) -> list[str]:
    """Select and truncate candidate translations in dictionary order.

    Returns the first ``limit`` unique (case-insensitive) non-empty candidates
    in the order the dictionary provided them, preserving original casing.

    Args:
        candidates: Raw translations from one or more dictionary backends.
        limit: Maximum number of results to return.

    Returns:
        Up to ``limit`` translations in dictionary order.
    """
    seen: set[str] = set()
    result: list[str] = []
    for raw in candidates:
        cand = raw.strip()
        if not cand:
            continue
        key = cand.lower()
        if key not in seen:
            seen.add(key)
            result.append(cand)
            if len(result) == limit:
                break
    return result
