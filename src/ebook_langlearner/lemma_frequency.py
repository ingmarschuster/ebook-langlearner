"""Lemma-aggregated Zipf frequency lookups.

:func:`wordfreq.zipf_frequency` scores surface forms in isolation, which
systematically underestimates how well-known a word's *lemma* is in
morphologically rich languages: "manger" has its frequency split across
dozens of conjugated forms, each individually rarer than the lemma-aggregate.

This module loads a precomputed table of lemma-aggregated Zipf values — built
offline by ``scripts/build_lemma_frequencies.py`` from the full wordfreq
wordlist folded onto :mod:`simplemma` lemmas — and exposes :func:`lemma_zipf`.
The table is loaded lazily per language (each file is under 2 MB gzipped) and
cached for the process lifetime.
"""

from __future__ import annotations

import gzip
import json
from functools import cache
from importlib import resources

from .frequency import ZIPF_UNKNOWN
from .languages import require_supported
from .tokenize import normalize_for_lookup

_DATA_PACKAGE = "ebook_langlearner.data"


@cache
def _load_table(lang: str) -> dict[str, float]:
    """Load and cache the lemma→Zipf table for ``lang``.

    Returns an empty dict if the data file is missing, which causes every
    lookup to return :data:`~ebook_langlearner.frequency.ZIPF_UNKNOWN` — a
    safe degradation equivalent to treating every lemma as OOV.
    """
    filename = f"lemma_freq_{lang}.json.gz"
    data_file = resources.files(_DATA_PACKAGE).joinpath(filename)
    if not data_file.is_file():
        return {}
    with data_file.open("rb") as raw, gzip.open(raw, "rt", encoding="utf-8") as gz:
        return json.load(gz)


def lemma_zipf(lemma: str, lang: str) -> float:
    """Return the lemma-aggregated Zipf frequency of ``lemma`` in ``lang``.

    The lemma is normalized (lowercased + NFC-composed) before lookup so that
    callers don't need to pre-normalize; this matches the behaviour of
    :func:`ebook_langlearner.tokenize.normalize_for_lookup`.

    Args:
        lemma: The lemma to score.
        lang: Two-letter ISO 639-1 code; must be in
            :data:`~ebook_langlearner.languages.CORE_LANGUAGES`.

    Returns:
        The aggregated Zipf frequency, or
        :data:`~ebook_langlearner.frequency.ZIPF_UNKNOWN` for OOV lemmas.
    """
    key = normalize_for_lookup(lemma)
    table = _load_table(require_supported(lang))
    return table.get(key, ZIPF_UNKNOWN)
