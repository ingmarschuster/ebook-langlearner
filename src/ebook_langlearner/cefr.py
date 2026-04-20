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
from functools import lru_cache
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
