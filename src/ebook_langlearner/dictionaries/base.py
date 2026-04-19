"""Dictionary interface and candidate ranking.

All backends implement :class:`Dictionary` and return *raw* candidate
translations for a lookup key; ranking (by target-language frequency) is done
uniformly by :func:`rank_candidates` so results are consistent across backends.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass

from ebook_langlearner.frequency import zipf


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

    Backends should return raw candidate translations in whatever order the
    source provides. Deduplication, casing preservation, and frequency-based
    ranking are applied uniformly by :func:`rank_candidates`.
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


def rank_candidates(candidates: list[str], target_lang: str, limit: int = 2) -> list[str]:
    """Rank and truncate candidate translations.

    Candidates are sorted by descending Zipf frequency in the target language,
    with ties broken by length (shorter first) and then alphabetically. This
    surfaces the most common, most-concise gloss first. Duplicates (case-
    insensitive) are collapsed, keeping the first casing observed.

    Args:
        candidates: Raw translations from one or more dictionary backends.
        target_lang: Language code used to score candidates via :func:`zipf`.
        limit: Maximum number of results to return.

    Returns:
        Up to ``limit`` translations in best-first order.
    """
    seen: dict[str, tuple[float, int, str]] = {}
    for raw in candidates:
        cand = raw.strip()
        if not cand:
            continue
        key = cand.lower()
        score = (-zipf(cand, target_lang), len(cand), cand.lower())
        if key not in seen or score < seen[key]:
            seen[key] = score
    ordered = sorted(seen.items(), key=lambda item: item[1])
    return [original for original, _score in _preserve_original_case(ordered, candidates)][:limit]


def _preserve_original_case(
    ordered_lower: list[tuple[str, tuple[float, int, str]]],
    originals: list[str],
) -> list[tuple[str, tuple[float, int, str]]]:
    """Restore the first observed casing for each ranked candidate.

    Ranking operates on lowercased keys; this helper ensures the returned
    strings keep the casing of the original input (important for nouns in
    languages where casing is semantic, e.g. German nouns).
    """
    first_case: dict[str, str] = {}
    for raw in originals:
        cand = raw.strip()
        if not cand:
            continue
        first_case.setdefault(cand.lower(), cand)
    return [(first_case.get(key, key), score) for key, score in ordered_lower]
