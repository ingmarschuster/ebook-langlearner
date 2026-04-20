"""Tests for the CEFR → Zipf cutoff lookup."""

from __future__ import annotations

import pytest

from ebook_langlearner.cefr import (
    CEFR_LEVELS,
    UnknownCEFRLevelError,
    cefr_cutoff,
    normalize_level,
)
from ebook_langlearner.languages import CORE_LANGUAGES, UnsupportedLanguageError


def test_cutoff_decreases_with_higher_level():
    """A C1 reader knows more words, so their cutoff must be *lower* than B1's.

    Stated in Zipf terms: annotating for a more advanced reader means only
    very rare words get wrapped, i.e. the cutoff sits further down the scale.
    """
    fr_b1 = cefr_cutoff("fr", "B1")
    fr_c1 = cefr_cutoff("fr", "C1")
    assert fr_c1 < fr_b1


def test_all_levels_and_languages_populated():
    for lang in CORE_LANGUAGES:
        for level in CEFR_LEVELS:
            value = cefr_cutoff(lang, level)
            assert 2.0 < value < 6.0, f"{lang}/{level} cutoff out of expected range: {value}"


def test_level_is_case_insensitive():
    assert cefr_cutoff("fr", "b1") == cefr_cutoff("fr", "B1")


def test_language_is_case_insensitive():
    assert cefr_cutoff("FR", "B1") == cefr_cutoff("fr", "B1")


def test_unknown_level_raises():
    with pytest.raises(UnknownCEFRLevelError):
        cefr_cutoff("fr", "D1")


def test_unsupported_language_raises():
    with pytest.raises(UnsupportedLanguageError):
        cefr_cutoff("xx", "B1")


def test_normalize_level_roundtrip():
    assert normalize_level("b2") == "B2"
