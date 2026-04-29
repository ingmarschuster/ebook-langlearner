"""Tests for the CEFR → Zipf cutoff lookup."""

from __future__ import annotations

import pytest

from ebook_langlearner.cefr import (
    CEFR_LEVELS,
    UnknownCEFRLevelError,
    cefr_cutoff,
    level_class,
    level_for_zipf,
    levels_revealed_at,
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


def test_level_for_zipf_returns_none_above_a1_cutoff():
    a1 = cefr_cutoff("fr", "A1")
    # Strictly above the A1 cutoff: a learner at any level already knows it.
    assert level_for_zipf("fr", a1 + 0.5) is None
    assert level_for_zipf("fr", a1) is None  # boundary: strict-greater-than


def test_level_for_zipf_picks_smallest_cutoff_still_greater():
    # A word at Zipf 4.5 in fr: cutoffs that exceed it are A1 (5.07), A2
    # (4.78) and B1 (4.515); the most-restrictive of those is B1.
    assert level_for_zipf("fr", 4.5) == "B1"
    # Very rare word: only C2 (3.266) still exceeds 0.0, so the word is
    # owned by C2.
    assert level_for_zipf("fr", 0.0) == "C2"


def test_levels_revealed_at_a1_includes_all():
    assert levels_revealed_at("a1") == CEFR_LEVELS


def test_levels_revealed_at_c2_only_includes_c2():
    assert levels_revealed_at("C2") == ("C2",)


def test_levels_revealed_at_b2_includes_b2_and_rarer():
    assert levels_revealed_at("b2") == ("B2", "C1", "C2")


def test_level_class_lowercases():
    assert level_class("B2") == "ell-level-b2"
    assert level_class("c1") == "ell-level-c1"
