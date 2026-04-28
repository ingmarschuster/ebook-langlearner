"""Tests for the SQLite-cached dict.cc index.

These tests cover the new ``ingest once, look up many times`` flow that
backs both the CLI's ``build-dictcc-index`` subcommand and the Calibre
plugin's settings panel. Each test monkeypatches the shared cache
directory to a ``tmp_path`` so nothing escapes the test environment.
"""

from __future__ import annotations

import os
from typing import TYPE_CHECKING

import pytest

from ebook_langlearner.dictionaries.base import LookupKey
from ebook_langlearner.dictionaries.dictcc import (
    DictCCIndex,
    build_dictcc_index,
    dictcc_index_path_for,
    ensure_dictcc_index,
    list_indexed_dictcc_pairs,
)

if TYPE_CHECKING:
    from pathlib import Path


@pytest.fixture
def isolated_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the shared cache directory to ``tmp_path`` for one test."""
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr("ebook_langlearner.dictionaries.wiktionary.cache_dir", lambda: cache)
    return cache


def test_index_path_uses_cache_dir(isolated_cache: Path):
    assert dictcc_index_path_for("fr", "en") == isolated_cache / "dictcc-fr-en.sqlite"


def test_build_then_lookup_roundtrip(isolated_cache: Path, tiny_dictcc_file: Path):
    index = build_dictcc_index(tiny_dictcc_file, "fr", "en")
    assert index == isolated_cache / "dictcc-fr-en.sqlite"
    assert index.exists()

    backend = DictCCIndex("fr", "en")
    assert backend.is_available
    candidates = backend.candidates(LookupKey(lemma="aubépine", source_lang="fr", target_lang="en"))
    # Two rows for aubépine in the fixture; the parenthetical "(tree)" is
    # stripped during parsing so both surface as plain "hawthorn".
    assert candidates == ["hawthorn", "hawthorn"]
    backend.close()


def test_index_returns_empty_for_wrong_direction(isolated_cache: Path, tiny_dictcc_file: Path):
    del isolated_cache
    build_dictcc_index(tiny_dictcc_file, "fr", "en")
    backend = DictCCIndex("fr", "en")
    assert backend.candidates(LookupKey("aubépine", source_lang="en", target_lang="fr")) == []
    assert backend.candidates(LookupKey("aubépine", source_lang="fr", target_lang="de")) == []
    backend.close()


def test_unavailable_index_is_silent(isolated_cache: Path):
    del isolated_cache  # the fixture redirects cache_dir, that's all we need
    backend = DictCCIndex("fr", "en")
    assert not backend.is_available
    assert backend.candidates(LookupKey("aubépine", source_lang="fr", target_lang="en")) == []


def test_build_replaces_existing_index(isolated_cache: Path, tiny_dictcc_file: Path):
    """Rebuilding must produce deterministic state, not append duplicate rows."""
    del isolated_cache
    build_dictcc_index(tiny_dictcc_file, "fr", "en")
    build_dictcc_index(tiny_dictcc_file, "fr", "en")
    backend = DictCCIndex("fr", "en")
    candidates = backend.candidates(LookupKey("aubépine", source_lang="fr", target_lang="en"))
    # The fixture has two rows for aubépine; rebuild should not double them.
    assert len(candidates) == 2
    backend.close()


def test_ensure_index_rebuilds_when_tsv_is_newer(
    isolated_cache: Path, tiny_dictcc_file: Path
):
    del isolated_cache
    index = ensure_dictcc_index(tiny_dictcc_file, "fr", "en")
    first_mtime = index.stat().st_mtime

    # Touch the TSV into the future so the index is now considered stale.
    future = first_mtime + 60
    os.utime(tiny_dictcc_file, (future, future))

    rebuilt = ensure_dictcc_index(tiny_dictcc_file, "fr", "en")
    assert rebuilt == index
    assert index.stat().st_mtime >= future


def test_ensure_index_skips_rebuild_when_fresh(
    isolated_cache: Path, tiny_dictcc_file: Path
):
    del isolated_cache
    index = ensure_dictcc_index(tiny_dictcc_file, "fr", "en")
    mtime_before = index.stat().st_mtime
    # Second call with the same inputs must be a pure no-op.
    again = ensure_dictcc_index(tiny_dictcc_file, "fr", "en")
    assert again == index
    assert index.stat().st_mtime == mtime_before


def test_build_merges_multiple_tsvs(isolated_cache: Path, tmp_path: Path):
    del isolated_cache
    a = tmp_path / "a.txt"
    b = tmp_path / "b.txt"
    a.write_text("aubépine\thawthorn\n", encoding="utf-8")
    b.write_text("aubépine\twhitethorn\n", encoding="utf-8")
    build_dictcc_index([a, b], "fr", "en")
    backend = DictCCIndex("fr", "en")
    assert sorted(
        backend.candidates(LookupKey("aubépine", source_lang="fr", target_lang="en"))
    ) == ["hawthorn", "whitethorn"]
    backend.close()


def test_list_indexed_pairs_finds_built_files(
    isolated_cache: Path, tiny_dictcc_file: Path
):
    del isolated_cache
    assert list_indexed_dictcc_pairs() == []
    build_dictcc_index(tiny_dictcc_file, "fr", "en")
    build_dictcc_index(tiny_dictcc_file, "de", "en")
    assert list_indexed_dictcc_pairs() == [("de", "en"), ("fr", "en")]


def test_list_indexed_pairs_ignores_unrelated_files(
    isolated_cache: Path, tiny_dictcc_file: Path
):
    build_dictcc_index(tiny_dictcc_file, "fr", "en")
    # Drop unrelated files in the cache to ensure the regex is strict.
    (isolated_cache / "wiktionary-fr.sqlite").write_bytes(b"")
    (isolated_cache / "kaikki-fr.jsonl").write_bytes(b"")
    (isolated_cache / "dictcc-broken.sqlite").write_bytes(b"")
    assert list_indexed_dictcc_pairs() == [("fr", "en")]
