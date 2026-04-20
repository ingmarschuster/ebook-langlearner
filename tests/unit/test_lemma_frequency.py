"""Tests for the precomputed lemma-aggregated Zipf table."""

from __future__ import annotations

import pytest

from ebook_langlearner.frequency import ZIPF_UNKNOWN, zipf
from ebook_langlearner.languages import UnsupportedLanguageError
from ebook_langlearner.lemma_frequency import lemma_zipf


def test_common_lemma_is_above_its_surface_form():
    """Aggregating inflections should push common verb lemmas above their surface Zipf.

    ``manger`` (infinitive "to eat") is fairly common in French but split
    across dozens of conjugations; its aggregated Zipf must exceed the Zipf
    of the bare infinitive form.
    """
    surface = zipf("manger", "fr")
    aggregated = lemma_zipf("manger", "fr")
    assert aggregated > surface, (
        f"aggregated lemma_zipf({aggregated}) must exceed surface zipf({surface})"
    )


def test_unknown_lemma_returns_zipf_unknown():
    assert lemma_zipf("zzxyqqqnotaword", "fr") == ZIPF_UNKNOWN


def test_lookup_is_normalized():
    """Callers should not have to pre-lowercase or NFC-compose the key."""
    assert lemma_zipf("Manger", "fr") == lemma_zipf("manger", "fr")


def test_unsupported_language_raises():
    with pytest.raises(UnsupportedLanguageError):
        lemma_zipf("manger", "xx")
