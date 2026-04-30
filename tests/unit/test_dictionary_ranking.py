"""Tests for the candidate selection helper."""

from __future__ import annotations

from ebook_langlearner.dictionaries.base import select_candidates


def test_preserves_dictionary_order():
    # Dictionary provides "feline" first — that must come back first.
    selected = select_candidates(["feline", "cat"], limit=2)
    assert selected == ["feline", "cat"]


def test_limit_caps_result_length():
    selected = select_candidates(["cat", "kitten", "feline"], limit=2)
    assert len(selected) == 2
    assert selected == ["cat", "kitten"]


def test_duplicates_collapsed_case_insensitively():
    selected = select_candidates(["Cat", "cat", "CAT"], limit=5)
    assert len(selected) == 1


def test_preserves_original_casing_of_first_occurrence():
    selected = select_candidates(["Weißdorn"], limit=1)
    assert selected == ["Weißdorn"]


def test_empty_input_returns_empty():
    assert select_candidates([], limit=2) == []


def test_whitespace_only_candidates_discarded():
    assert select_candidates(["  ", "", "cat"], limit=2) == ["cat"]
