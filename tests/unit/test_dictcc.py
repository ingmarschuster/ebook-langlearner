"""Tests for the dict.cc parser."""

from __future__ import annotations

from typing import TYPE_CHECKING

from ebook_langlearner.dictionaries.base import LookupKey

if TYPE_CHECKING:
    from ebook_langlearner.dictionaries.dictcc import DictCCDictionary


def test_loads_entries_and_looks_them_up(dictcc_fr_en: DictCCDictionary):
    key = LookupKey(lemma="aubépine", source_lang="fr", target_lang="en")
    candidates = dictcc_fr_en.candidates(key)
    # The fixture has two lines for aubépine; the second's parenthetical
    # disambiguator "(tree)" is stripped, leaving two "hawthorn" entries.
    assert candidates == ["hawthorn", "hawthorn"]


def test_strips_curly_annotations_from_headword(dictcc_fr_en: DictCCDictionary):
    # "crépuscule" appears as headword with {m} — the {m} must be stripped.
    key = LookupKey(lemma="crépuscule", source_lang="fr", target_lang="en")
    assert "twilight" in dictcc_fr_en.candidates(key)


def test_language_pair_mismatch_returns_empty(dictcc_fr_en: DictCCDictionary):
    wrong_direction = LookupKey(lemma="aubépine", source_lang="en", target_lang="fr")
    assert dictcc_fr_en.candidates(wrong_direction) == []


def test_unknown_lemma_returns_empty(dictcc_fr_en: DictCCDictionary):
    key = LookupKey(lemma="zzzzzzz", source_lang="fr", target_lang="en")
    assert dictcc_fr_en.candidates(key) == []


def test_parsing_survives_malformed_lines(dictcc_fr_en: DictCCDictionary):
    # The fixture file contains an empty-field line and a one-field "badline";
    # the parser must still load the real entries.
    key = LookupKey(lemma="aubépine", source_lang="fr", target_lang="en")
    assert dictcc_fr_en.candidates(key)
