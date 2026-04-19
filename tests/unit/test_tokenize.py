"""Tests for the tokenizer and word-classification heuristics."""

from __future__ import annotations

from ebook_langlearner.tokenize import (
    Token,
    is_numeric,
    is_sentence_boundary,
    is_too_short,
    looks_like_proper_noun,
    normalize_for_lookup,
    tokenize,
)


def test_tokenize_reconstructs_original_text():
    text = "Le crépuscule tombe sur l'aubépine."
    tokens = tokenize(text)
    assert "".join(t.text for t in tokens) == text


def test_tokenize_separates_words_and_punctuation():
    tokens = tokenize("Hello, world!")
    words = [t.text for t in tokens if t.is_word]
    assert words == ["Hello", "world"]


def test_tokenize_keeps_hyphenated_forms_together():
    tokens = tokenize("peut-être")
    words = [t.text for t in tokens if t.is_word]
    assert words == ["peut-être"]


def test_tokenize_splits_french_elision_on_apostrophe():
    tokens = tokenize("l'arbre")
    words = [t.text for t in tokens if t.is_word]
    assert words == ["l", "arbre"]


def test_tokenize_splits_typographic_apostrophe_too():
    tokens = tokenize("l\u2019arbre")
    words = [t.text for t in tokens if t.is_word]
    assert words == ["l", "arbre"]


def test_tokenize_empty_string_returns_empty_list():
    assert tokenize("") == []


def test_token_is_word_distinguishes_punctuation():
    assert Token("hello", 0, 5).is_word
    assert not Token("   ", 0, 3).is_word
    assert not Token("...", 0, 3).is_word


def test_looks_like_proper_noun_skips_sentence_start():
    assert not looks_like_proper_noun("Paris", sentence_start=True)
    assert looks_like_proper_noun("Paris", sentence_start=False)


def test_looks_like_proper_noun_ignores_leading_punctuation():
    assert looks_like_proper_noun("«Paris", sentence_start=False)


def test_looks_like_proper_noun_lowercase_never_flagged():
    assert not looks_like_proper_noun("paris", sentence_start=False)


def test_is_numeric_flags_any_digit():
    assert is_numeric("2024")
    assert is_numeric("3rd")
    assert not is_numeric("three")


def test_is_too_short_respects_min_length():
    assert is_too_short("a")
    assert not is_too_short("ab")
    assert is_too_short("ab", min_length=3)


def test_normalize_for_lookup_lowercases_and_composes():
    # "café" written decomposed: c, a, f, e + combining acute.
    decomposed = "cafe\u0301"
    assert normalize_for_lookup(decomposed) == "café"
    assert normalize_for_lookup("CAFÉ") == "café"


def test_is_sentence_boundary_detects_period_then_space():
    assert is_sentence_boundary(". ")
    assert is_sentence_boundary("! ")
    assert is_sentence_boundary("? ")
    assert is_sentence_boundary("")  # start of input
    assert not is_sentence_boundary(", ")
    assert not is_sentence_boundary(" ")  # whitespace after mid-sentence word
