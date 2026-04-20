"""Tests for the candidate ranking helper."""

from __future__ import annotations

from ebook_langlearner.dictionaries.base import rank_candidates


def test_ranks_more_common_translation_first():
    # "cat" is far more frequent than "feline" in English.
    ranked = rank_candidates(["feline", "cat"], target_lang="en", limit=2)
    assert ranked == ["cat", "feline"]


def test_limit_caps_result_length():
    ranked = rank_candidates(["cat", "kitten", "feline"], target_lang="en", limit=2)
    assert len(ranked) == 2


def test_duplicates_collapsed_case_insensitively():
    ranked = rank_candidates(["Cat", "cat", "CAT"], target_lang="en", limit=5)
    assert len(ranked) == 1


def test_preserves_original_casing_of_first_occurrence():
    # "Weißdorn" should come back as "Weißdorn", not "weißdorn".
    ranked = rank_candidates(["Weißdorn"], target_lang="de", limit=1)
    assert ranked == ["Weißdorn"]


def test_empty_input_returns_empty():
    assert rank_candidates([], target_lang="en", limit=2) == []


def test_whitespace_only_candidates_discarded():
    assert rank_candidates(["  ", "", "cat"], target_lang="en", limit=2) == ["cat"]
