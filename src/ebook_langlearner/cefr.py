"""CEFR-level to Zipf-cutoff lookup.

The annotator works in Zipf space: a word is annotated when its
lemma-aggregated Zipf is below the configured cutoff. Language learners
think in CEFR levels (A1-C2), so this module maps between the two using a
precomputed per-language table built by ``scripts/build_cefr_cutoffs.py``.

Why per-language: the Zipf value at which the N-th most common lemma sits
varies across languages because of morphological richness — the same CEFR
level corresponds to different Zipf cutoffs in French vs. German vs. Polish.
Using one hand-picked cutoff across languages would systematically
under-annotate some languages and over-annotate others.
"""

from __future__ import annotations

import json
from functools import cache, lru_cache
from importlib import resources

from .languages import require_supported

_DATA_PACKAGE = "ebook_langlearner.data"
_CUTOFFS_FILE = "cefr_cutoffs.json"

CEFR_LEVELS: tuple[str, ...] = ("A1", "A2", "B1", "B2", "C1", "C2")
"""Supported CEFR levels, ordered from lowest to highest proficiency."""


class UnknownCEFRLevelError(ValueError):
    """Raised when a CEFR level string is not one of :data:`CEFR_LEVELS`."""


@lru_cache(maxsize=1)
def _load_cutoffs() -> dict[str, dict[str, float]]:
    """Load and cache the CEFR cutoff table.

    Returns a nested mapping ``{lang: {level: zipf}}``. Raises if the data
    file is missing, since unlike the lemma-frequency table this one is a
    few hundred bytes and there's no graceful fallback: without it ``--level``
    cannot function.
    """
    data_file = resources.files(_DATA_PACKAGE).joinpath(_CUTOFFS_FILE)
    with data_file.open("rb") as raw:
        return json.load(raw)


def normalize_level(level: str) -> str:
    """Uppercase and validate a CEFR level string.

    Args:
        level: Case-insensitive CEFR level, e.g. ``"b1"`` or ``"B1"``.

    Returns:
        The uppercased level.

    Raises:
        UnknownCEFRLevelError: If ``level`` is not in :data:`CEFR_LEVELS`.
    """
    upper = level.upper()
    if upper not in CEFR_LEVELS:
        allowed = ", ".join(CEFR_LEVELS)
        msg = f"Unknown CEFR level {level!r}; expected one of {allowed}."
        raise UnknownCEFRLevelError(msg)
    return upper


def cefr_cutoff(lang: str, level: str) -> float:
    """Return the Zipf cutoff for ``lang`` at CEFR ``level``.

    The cutoff is the lemma-aggregated Zipf of the N-th most common lemma in
    ``lang``, where N is the CEFR receptive-vocabulary-size target for
    ``level`` (see :mod:`scripts.build_cefr_cutoffs`). Words with
    lemma-Zipf strictly below this cutoff should be annotated for a reader
    at ``level``.

    Args:
        lang: Source language code (case-insensitive). Must be in
            :data:`~ebook_langlearner.languages.CORE_LANGUAGES`.
        level: CEFR level string (case-insensitive), e.g. ``"B1"``.

    Returns:
        The Zipf cutoff calibrated for this language and level.
    """
    lang = require_supported(lang)
    level = normalize_level(level)
    return _load_cutoffs()[lang][level]


@cache
def _levels_with_cutoffs(lang: str) -> tuple[tuple[str, float], ...]:
    """Return ``((level, cutoff), …)`` for ``lang`` sorted by cutoff descending.

    A1 has the largest cutoff and C2 the smallest, so iterating this tuple
    walks the levels from most permissive to most restrictive.
    """
    lang = require_supported(lang)
    table = _load_cutoffs()[lang]
    return tuple(sorted(table.items(), key=lambda kv: kv[1], reverse=True))


def level_for_zipf(lang: str, zipf_value: float) -> str | None:
    """Return the CEFR level that "owns" a word with Zipf ``zipf_value``.

    A word is owned by the *most restrictive* level whose cutoff is still
    strictly greater than ``zipf_value`` — equivalently, the smallest cutoff
    that would still annotate this word. A learner at that level (or any
    more permissive one) needs the annotation; a stricter learner already
    knows the word.

    Args:
        lang: Source language code (case-insensitive).
        zipf_value: Lemma-aggregated Zipf frequency of the word.

    Returns:
        The owning CEFR level (uppercase, e.g. ``"B1"``), or ``None`` when
        no level's cutoff exceeds ``zipf_value`` (the word is common enough
        that even the most permissive level — A1 — doesn't annotate it).
    """
    candidate: str | None = None
    for level, cutoff in _levels_with_cutoffs(lang):
        if cutoff > zipf_value:
            candidate = level
    return candidate


def levels_revealed_at(active_level: str) -> tuple[str, ...]:
    """Return the CEFR levels whose annotations should be visible at ``active_level``.

    A learner at ``active_level`` sees annotations for every word their level
    *or* a stricter (rarer-targeting) level would annotate — i.e. every level
    in :data:`CEFR_LEVELS` from ``active_level`` upward. A1 reveals all six
    levels; C2 reveals only itself.

    Args:
        active_level: CEFR level string (case-insensitive).

    Returns:
        Tuple of CEFR levels (uppercase) in canonical A1→C2 order.
    """
    active = normalize_level(active_level)
    start = CEFR_LEVELS.index(active)
    return CEFR_LEVELS[start:]


def level_class(level: str) -> str:
    """Return the CSS class suffix for a CEFR ``level``.

    Args:
        level: CEFR level string (case-insensitive).

    Returns:
        The class name, e.g. ``"ell-level-b2"``.
    """
    return f"ell-level-{normalize_level(level).lower()}"
