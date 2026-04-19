"""Shared pytest fixtures and helpers."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from ebook_langlearner.dictionaries.base import Dictionary
from ebook_langlearner.dictionaries.dictcc import DictCCDictionary
from ebook_langlearner.dictionaries.wiktionary import WiktionaryDictionary, build_index

if TYPE_CHECKING:
    from ebook_langlearner.dictionaries.base import LookupKey


SAMPLES_DIR = Path(__file__).resolve().parent.parent / "samples"
CANDIDE_PATH = SAMPLES_DIR / "candide.epub"


class _StaticDictionary(Dictionary):
    """Dictionary backend that returns canned results keyed by (lemma, target)."""

    def __init__(
        self,
        source_lang: str,
        data: dict[tuple[str, str], list[str]],
    ) -> None:
        self._source_lang = source_lang
        self._data = data

    def candidates(self, key: LookupKey) -> list[str]:
        if key.source_lang != self._source_lang:
            return []
        return list(self._data.get((key.lemma, key.target_lang), []))


class _PermissiveDictionary(Dictionary):
    """Dictionary backend that returns a constant translation for any lemma.

    Useful for end-to-end tests where we want to exercise the pipeline on a
    real book without depending on coverage of a particular wordlist.
    """

    def __init__(self, source_lang: str, translation: str = "TR") -> None:
        self._source_lang = source_lang
        self._translation = translation

    def candidates(self, key: LookupKey) -> list[str]:
        if key.source_lang != self._source_lang:
            return []
        return [self._translation]


@pytest.fixture
def permissive_fr_dict() -> Dictionary:
    """Return a dictionary that maps any French lemma to a fixed English token."""
    return _PermissiveDictionary("fr", translation="TR")


@pytest.fixture
def static_dict_factory():
    """Build a tiny in-memory :class:`Dictionary` for use in annotator tests."""

    def _factory(
        source_lang: str,
        data: dict[tuple[str, str], list[str]],
    ) -> Dictionary:
        return _StaticDictionary(source_lang, data)

    return _factory


@pytest.fixture
def tiny_dictcc_file(tmp_path: Path) -> Path:
    """Write a small dict.cc-style export for FR→EN and return its path."""
    lines = [
        "# dict.cc tiny fixture",
        "aubépine\thawthorn\t{f}\tbotanics",
        "aubépine\thawthorn (tree)\t{f}\tbotanics",
        "crépuscule\ttwilight\t{m}\t",
        "crépuscule\tdusk\t{m}\t",
        "\t\t\t",
        "badline",
    ]
    path = tmp_path / "fr-en.txt"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


@pytest.fixture
def tiny_wiktionary_index(tmp_path: Path) -> Path:
    """Build a tiny Kaikki-style JSONL file and return a built SQLite index path."""
    entries = [
        {
            "word": "aubépine",
            "senses": [],
            "translations": [
                {"lang": "English", "code": "en", "word": "hawthorn"},
                {"lang": "German", "code": "de", "word": "Weißdorn"},
            ],
        },
        {
            "word": "crépuscule",
            "translations": [
                {"lang": "English", "code": "en", "word": "twilight"},
                {"lang": "English", "code": "en", "word": "dusk"},
            ],
        },
    ]
    jsonl_path = tmp_path / "fr.jsonl"
    jsonl_path.write_text("\n".join(json.dumps(e) for e in entries) + "\n", encoding="utf-8")
    index_path = tmp_path / "fr.sqlite"
    build_index("fr", jsonl_path, index_path=index_path)
    return index_path


@pytest.fixture
def minimal_epub(tmp_path: Path) -> Path:
    """Return a working copy of the committed Candide sample.

    The pipeline must survive round-tripping through :mod:`ebooklib` on real
    EPUBs, so we use the committed Project-Gutenberg Candide file as the
    integration fixture rather than hand-constructing one. Hand-built EPUBs
    expose ebooklib round-trip bugs (uid loss on TOC links) that don't occur
    on well-formed real-world books.
    """
    if not CANDIDE_PATH.exists():
        pytest.skip(f"sample EPUB missing at {CANDIDE_PATH}")
    destination = tmp_path / "source.epub"
    shutil.copy(CANDIDE_PATH, destination)
    return destination


@pytest.fixture
def dictcc_fr_en(tiny_dictcc_file: Path) -> DictCCDictionary:
    """Load the tiny dict.cc fixture as a French→English dictionary."""
    return DictCCDictionary.from_file(tiny_dictcc_file, source_lang="fr", target_lang="en")


@pytest.fixture
def wiktionary_fr(tiny_wiktionary_index: Path) -> WiktionaryDictionary:
    """Open a WiktionaryDictionary against the fixture SQLite index."""
    dictionary = WiktionaryDictionary("fr", index_path=tiny_wiktionary_index)
    yield dictionary
    dictionary.close()
