"""Tests for the composite dictionary."""

from __future__ import annotations

import pytest

from ebook_langlearner.dictionaries.base import LookupKey
from ebook_langlearner.dictionaries.composite import CompositeDictionary


def test_first_backend_with_result_wins(static_dict_factory):
    primary = static_dict_factory("fr", {("chat", "en"): ["cat"]})
    secondary = static_dict_factory("fr", {("chat", "en"): ["feline"]})
    composite = CompositeDictionary([primary, secondary])
    assert composite.candidates(
        LookupKey(lemma="chat", source_lang="fr", target_lang="en")
    ) == ["cat"]


def test_falls_through_to_next_backend_when_primary_empty(static_dict_factory):
    primary = static_dict_factory("fr", {})  # no entries
    secondary = static_dict_factory("fr", {("chat", "en"): ["cat"]})
    composite = CompositeDictionary([primary, secondary])
    assert composite.candidates(
        LookupKey(lemma="chat", source_lang="fr", target_lang="en")
    ) == ["cat"]


def test_returns_empty_when_no_backend_matches(static_dict_factory):
    composite = CompositeDictionary([static_dict_factory("fr", {})])
    assert (
        composite.candidates(
            LookupKey(lemma="chat", source_lang="fr", target_lang="en")
        )
        == []
    )


def test_empty_backend_list_rejected():
    with pytest.raises(ValueError, match="at least one backend"):
        CompositeDictionary([])
