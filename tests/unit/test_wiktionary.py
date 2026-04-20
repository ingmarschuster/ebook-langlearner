"""Tests for the Wiktionary/Kaikki SQLite-backed backend."""

from __future__ import annotations

from ebook_langlearner.dictionaries.base import LookupKey
from ebook_langlearner.dictionaries.wiktionary import WiktionaryDictionary


def test_index_marks_itself_available(wiktionary_fr: WiktionaryDictionary):
    assert wiktionary_fr.is_available


def test_lookup_returns_translations_for_target_language(
    wiktionary_fr: WiktionaryDictionary,
):
    key = LookupKey(lemma="crépuscule", source_lang="fr", target_lang="en")
    assert wiktionary_fr.candidates(key) == ["twilight", "dusk"]


def test_lookup_filters_by_target_language(wiktionary_fr: WiktionaryDictionary):
    # "aubépine" has EN and DE translations in the fixture.
    en = wiktionary_fr.candidates(
        LookupKey(lemma="aubépine", source_lang="fr", target_lang="en")
    )
    de = wiktionary_fr.candidates(
        LookupKey(lemma="aubépine", source_lang="fr", target_lang="de")
    )
    assert en == ["hawthorn"]
    assert de == ["Weißdorn"]


def test_missing_source_language_returns_empty(wiktionary_fr: WiktionaryDictionary):
    # The dictionary is French-source; asking for an English lemma returns [].
    assert (
        wiktionary_fr.candidates(
            LookupKey(lemma="hawthorn", source_lang="en", target_lang="de")
        )
        == []
    )


def test_missing_index_file_keeps_dictionary_unavailable(tmp_path):
    nonexistent = tmp_path / "does-not-exist.sqlite"
    dictionary = WiktionaryDictionary("fr", index_path=nonexistent)
    assert not dictionary.is_available
    assert (
        dictionary.candidates(LookupKey(lemma="x", source_lang="fr", target_lang="en"))
        == []
    )
