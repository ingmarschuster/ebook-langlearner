"""Tests for the language whitelist and validator."""

from __future__ import annotations

import pytest

from ebook_langlearner.languages import (
    CORE_LANGUAGES,
    UnsupportedLanguageError,
    require_supported,
)


def test_core_languages_include_expected_set():
    assert {"en", "de", "fr", "es", "it", "nl", "pt", "pl", "sv"} <= set(CORE_LANGUAGES)


def test_require_supported_normalizes_case():
    assert require_supported("FR") == "fr"


def test_require_supported_rejects_unknown():
    with pytest.raises(UnsupportedLanguageError):
        require_supported("xx")
