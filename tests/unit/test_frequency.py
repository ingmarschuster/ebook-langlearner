"""Tests for the wordfreq wrapper."""

from __future__ import annotations

from ebook_langlearner.frequency import ZIPF_UNKNOWN, is_rare, zipf


def test_common_word_has_high_zipf():
    # "the" is one of the most common English words.
    assert zipf("the", "en") > 7.0


def test_unknown_word_returns_zero():
    assert zipf("zzxyqqqnotaword", "en") == ZIPF_UNKNOWN


def test_is_rare_respects_cutoff():
    assert not is_rare("the", "en", cutoff=3.0)
    # "hawthorn" is relatively rare — should be below cutoff 4.0.
    assert is_rare("hawthorn", "en", cutoff=4.0)


def test_oov_always_rare_when_cutoff_positive():
    assert is_rare("zzxyqqqnotaword", "en", cutoff=0.5)
    # At cutoff 0 the strict-less-than comparison does not flag OOV words.
    assert not is_rare("zzxyqqqnotaword", "en", cutoff=0.0)
