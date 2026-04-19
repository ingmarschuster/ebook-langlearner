"""Word-frequency lookups backed by :mod:`wordfreq`.

All frequencies are returned on the Zipf scale used by wordfreq, which ranges
roughly from ``0.0`` (out-of-vocabulary) to ``8.0`` (extremely common — e.g.
articles and pronouns). Typical "rare" cutoffs for language learners fall
between ``2.5`` and ``4.0``.
"""

from __future__ import annotations

from wordfreq import zipf_frequency

ZIPF_UNKNOWN = 0.0
"""Zipf value returned by :mod:`wordfreq` for out-of-vocabulary words."""


def zipf(word: str, lang: str) -> float:
    """Return the Zipf frequency of ``word`` in ``lang``.

    Args:
        word: The surface form or lemma to look up. :mod:`wordfreq` performs
            its own casing/diacritic handling internally.
        lang: A two-letter ISO 639-1 language code supported by :mod:`wordfreq`.

    Returns:
        The Zipf frequency, or ``0.0`` if the word is unknown.
    """
    return zipf_frequency(word, lang, wordlist="best")


def is_rare(word: str, lang: str, cutoff: float) -> bool:
    """Check whether ``word`` is below the rarity cutoff.

    A word is rare if its Zipf frequency is strictly less than ``cutoff``. OOV
    words (Zipf ``0.0``) are therefore rare whenever ``cutoff > 0``.

    Args:
        word: Word or lemma to check.
        lang: Source language code.
        cutoff: Zipf cutoff. Words below this value are rare.

    Returns:
        ``True`` if the word should be considered rare.
    """
    return zipf(word, lang) < cutoff
