"""Wiktionary dictionary backed by Kaikki.org JSONL extractions.

`Kaikki.org <https://kaikki.org>`_ publishes one JSONL file per Wiktionary
language edition. Each line is a JSON object representing one word entry with
the shape::

    {"word": "...", "senses": [...], "translations": [{"lang": "...", "code": "de", "word": "..."}]}

Because a single source language's Wiktionary typically contains translations
into dozens of target languages, one Kaikki dump covers *many* pairs. On first
use we build a SQLite index keyed by ``(word_norm, target_code)`` in the user's
cache directory; subsequent lookups are O(log n) per query.
"""

from __future__ import annotations

import gzip
import json
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from platformdirs import user_cache_path

from ebook_langlearner.tokenize import normalize_for_lookup

from .base import Dictionary

if TYPE_CHECKING:
    from collections.abc import Iterable
    from typing import BinaryIO

    from .base import LookupKey


def cache_dir() -> Path:
    """Return the user cache directory for this application, creating it if needed.

    Uses :mod:`platformdirs` so the location is appropriate per OS
    (``~/.cache/ebook-langlearner`` on Linux, etc.).
    """
    path = user_cache_path("ebook-langlearner", appauthor=False)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _index_path(source_lang: str) -> Path:
    """Default on-disk location for a source-language SQLite index."""
    return cache_dir() / f"wiktionary-{source_lang}.sqlite"


def _iter_entries(fh: BinaryIO) -> Iterable[dict]:
    """Yield parsed JSON objects from a Kaikki JSONL stream, tolerating bad lines."""
    for raw in fh:
        line = raw.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue


def build_index(
    source_lang: str,
    jsonl_path: Path | str,
    *,
    index_path: Path | None = None,
) -> Path:
    """Build a SQLite translation index from a Kaikki JSONL dump.

    Any existing index at the target location is removed and recreated. The
    file may be plain JSONL or gzipped (``.gz`` suffix).

    Args:
        source_lang: ISO 639-1 code identifying which Wiktionary edition the
            dump was extracted from.
        jsonl_path: Path to the ``.jsonl`` or ``.jsonl.gz`` file.
        index_path: Optional override for the output SQLite path. Defaults to
            the per-user cache location returned by :func:`cache_dir`.

    Returns:
        The path to the built SQLite index.
    """
    jsonl_path = Path(jsonl_path)
    if index_path is None:
        index_path = _index_path(source_lang)
    if index_path.exists():
        index_path.unlink()

    conn = sqlite3.connect(index_path)
    try:
        conn.execute("PRAGMA journal_mode=OFF")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute(
            "CREATE TABLE translations ("
            "word_norm TEXT NOT NULL, "
            "target TEXT NOT NULL, "
            "translation TEXT NOT NULL)"
        )
        opener = gzip.open if jsonl_path.suffix == ".gz" else open
        with opener(jsonl_path, "rb") as fh:
            conn.executemany(
                "INSERT INTO translations(word_norm, target, translation) VALUES(?, ?, ?)",
                _translation_rows(_iter_entries(fh)),
            )
        conn.execute("CREATE INDEX idx_translations_lookup ON translations(word_norm, target)")
        conn.commit()
    finally:
        conn.close()
    return index_path


def _translation_rows(entries: Iterable[dict]) -> Iterable[tuple[str, str, str]]:
    """Flatten entries into ``(word_norm, target_code, translation)`` rows."""
    for entry in entries:
        word = entry.get("word")
        if not isinstance(word, str) or not word:
            continue
        word_norm = normalize_for_lookup(word)
        for tr in entry.get("translations", []) or []:
            code = tr.get("code")
            term = tr.get("word")
            if not code or not term:
                continue
            yield word_norm, code.lower(), term


class WiktionaryDictionary(Dictionary):
    """SQLite-backed Wiktionary dictionary for a single source language.

    One source language corresponds to one SQLite index file (built via
    :func:`build_index`). A single :class:`WiktionaryDictionary` can answer
    queries for *any* target language present in the dump.
    """

    def __init__(self, source_lang: str, index_path: Path | None = None) -> None:
        """Create a dictionary pointing at the given index file.

        Args:
            source_lang: ISO 639-1 code identifying which source-language
                Wiktionary dump backs this dictionary.
            index_path: Optional explicit index path. Defaults to the per-user
                cache location.
        """
        self._source_lang = source_lang.lower()
        self._index_path = index_path or _index_path(source_lang)
        self._conn: sqlite3.Connection | None = None

    @property
    def is_available(self) -> bool:
        """Whether the backing SQLite index exists on disk."""
        return self._index_path.exists()

    def _connection(self) -> sqlite3.Connection | None:
        """Open the SQLite connection lazily, or return None if unavailable."""
        if not self.is_available:
            return None
        if self._conn is None:
            self._conn = sqlite3.connect(self._index_path)
        return self._conn

    def candidates(self, key: LookupKey) -> list[str]:
        """Return all translations recorded in Wiktionary for this lookup.

        Returns ``[]`` if the source language does not match this dictionary's
        source language, or if the SQLite index does not exist yet.

        Args:
            key: The lookup key.

        Returns:
            Translations in the order they were stored in the index (which
            matches the order in the source JSONL).
        """
        if key.source_lang.lower() != self._source_lang:
            return []
        conn = self._connection()
        if conn is None:
            return []
        rows = conn.execute(
            "SELECT translation FROM translations WHERE word_norm = ? AND target = ?",
            (normalize_for_lookup(key.lemma), key.target_lang.lower()),
        ).fetchall()
        return [row[0] for row in rows]

    def close(self) -> None:
        """Close the underlying SQLite connection, if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
