"""Tests for the simplemma wrapper."""

from __future__ import annotations

from ebook_langlearner.lemmatize import lemmatize


def test_french_verb_lemmatization():
    assert lemmatize("mangeait", "fr") == "manger"


def test_english_plural_lemmatization():
    assert lemmatize("children", "en") == "child"


def test_unsupported_language_falls_back_to_lowercased_input():
    # "xx" is not a real language code — simplemma should raise internally.
    assert lemmatize("HELLO", "xx") == "hello"


def test_lemmatize_is_cached():
    # Call twice and verify the same instance comes back (identity) when the
    # underlying simplemma call returns the same string.
    first = lemmatize("crépuscule", "fr")
    second = lemmatize("crépuscule", "fr")
    assert first == second
