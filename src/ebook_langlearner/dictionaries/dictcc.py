"""Parser and SQLite cache for dict.cc tab-separated export files.

dict.cc publishes user-downloadable exports with one translation pair per line.
Each line contains four tab-separated fields, in this order:

1. source term
2. target term
3. part of speech
4. category

Any of the fields may contain curly-, square-, or angle-bracket annotations
(e.g. ``{m}`` for gender, ``[ling.]`` for domain, ``<syn>`` for a synonym) and
parenthetical disambiguators. These are stripped before the term is stored so
that lookups match against the clean headword.

Each export covers a single language direction. The TSV is parsed once via
:func:`build_dictcc_index` into a SQLite file under the user cache directory;
:class:`DictCCIndex` is the runtime backend that reads from that cache, so
repeat runs across multiple books pay the parse cost only on the first build.
"""

from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path
from typing import TYPE_CHECKING

from ebook_langlearner.tokenize import normalize_for_lookup

from . import wiktionary as _wiktionary
from .base import Dictionary

if TYPE_CHECKING:
    from collections.abc import Iterable, Sequence

    from .base import LookupKey

_ANNOTATION_RE = re.compile(r"\s*[\[\{<][^\]\}>]*[\]\}>]\s*")
_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*")
_INDEX_FILE_RE = re.compile(r"^dictcc-([a-z]{2,3})-([a-z]{2,3})\.sqlite$")

_MIN_FIELDS_PER_LINE = 2


def _clean(term: str) -> str:
    """Remove bracketed and parenthetical annotations and collapse whitespace."""
    term = _ANNOTATION_RE.sub(" ", term)
    term = _PAREN_RE.sub(" ", term)
    return " ".join(term.split())


def iter_dictcc_pairs(path: Path | str) -> Iterable[tuple[str, str]]:
    """Yield ``(word_norm, translation)`` pairs from a dict.cc TSV export.

    Lines beginning with ``#``, blank lines, and lines with fewer than two
    tab-separated fields are skipped silently — dict.cc exports occasionally
    contain partial rows and the caller should not have to reject the whole
    file because of one bad line.

    Args:
        path: Filesystem path to a tab-separated dict.cc export.

    Yields:
        Pairs of ``(normalized_source_lemma, cleaned_translation)`` ready to
        be loaded into either an in-memory dict or a SQLite index.
    """
    with Path(path).open(encoding="utf-8") as fh:
        for raw in fh:
            line = raw.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            parts = line.split("\t")
            if len(parts) < _MIN_FIELDS_PER_LINE:
                continue
            src_clean = _clean(parts[0])
            tgt_clean = _clean(parts[1])
            if not src_clean or not tgt_clean:
                continue
            yield normalize_for_lookup(src_clean), tgt_clean


def dictcc_index_path_for(source_lang: str, target_lang: str) -> Path:
    """Return the on-disk SQLite cache path for a ``(source, target)`` pair.

    The file is not guaranteed to exist; callers can check with
    :meth:`Path.exists` or :func:`ensure_dictcc_index` to build it.

    Args:
        source_lang: ISO 639-1 source-language code.
        target_lang: ISO 639-1 target-language code.

    Returns:
        ``<cache_dir>/dictcc-<src>-<tgt>.sqlite``.
    """
    return _wiktionary.cache_dir() / f"dictcc-{source_lang.lower()}-{target_lang.lower()}.sqlite"


def build_dictcc_index(
    tsv_paths: Sequence[Path | str] | Path | str,
    source_lang: str,
    target_lang: str,
    *,
    index_path: Path | None = None,
) -> Path:
    """Build a SQLite cache from one or more dict.cc TSV exports.

    Multiple TSV inputs are merged into a single index; each pair is stored
    as its own row so a headword with several translations stays multi-valued
    after lookup. Any pre-existing index at the destination is replaced so
    rebuilds are deterministic.

    Args:
        tsv_paths: A single path or a sequence of paths to dict.cc TSV files.
            All paths must cover the same ``(source_lang, target_lang)``
            direction; the builder does not validate that.
        source_lang: ISO 639-1 source-language code (used only to derive the
            default ``index_path``).
        target_lang: ISO 639-1 target-language code (used only to derive the
            default ``index_path``).
        index_path: Optional override for the output SQLite path. Defaults to
            :func:`dictcc_index_path_for`.

    Returns:
        The path to the built SQLite index.
    """
    if isinstance(tsv_paths, (str, Path)):
        tsv_paths = [tsv_paths]
    if index_path is None:
        index_path = dictcc_index_path_for(source_lang, target_lang)
    if index_path.exists():
        index_path.unlink()

    conn = sqlite3.connect(index_path)
    try:
        conn.execute("PRAGMA journal_mode=OFF")
        conn.execute("PRAGMA synchronous=OFF")
        conn.execute("CREATE TABLE entries (word_norm TEXT NOT NULL, translation TEXT NOT NULL)")
        for path in tsv_paths:
            conn.executemany(
                "INSERT INTO entries(word_norm, translation) VALUES(?, ?)",
                iter_dictcc_pairs(path),
            )
        conn.execute("CREATE INDEX idx_entries_word ON entries(word_norm)")
        conn.commit()
    finally:
        conn.close()
    return index_path


def ensure_dictcc_index(
    tsv_paths: Sequence[Path | str] | Path | str,
    source_lang: str,
    target_lang: str,
) -> Path:
    """Return the cached SQLite path, rebuilding if missing or out of date.

    The index is considered stale if any of the input TSV files has a newer
    ``mtime`` than the cached SQLite — that way users who refresh their
    dict.cc download don't have to remember to manually rebuild.

    Args:
        tsv_paths: One or more paths to dict.cc TSV exports.
        source_lang: ISO 639-1 source-language code.
        target_lang: ISO 639-1 target-language code.

    Returns:
        Path to the cached SQLite index.
    """
    if isinstance(tsv_paths, (str, Path)):
        tsv_paths = [tsv_paths]
    paths = [Path(p) for p in tsv_paths]
    index_path = dictcc_index_path_for(source_lang, target_lang)
    latest_tsv = max(p.stat().st_mtime for p in paths)
    if index_path.exists() and latest_tsv <= index_path.stat().st_mtime:
        return index_path
    built = build_dictcc_index(paths, source_lang, target_lang, index_path=index_path)
    # Pin the index's mtime to at least the newest TSV so a second call
    # with the same inputs doesn't trigger another rebuild when a TSV's
    # mtime is in the future (manual touch, restore-from-backup, ...).
    if built.stat().st_mtime < latest_tsv:
        os.utime(built, (latest_tsv, latest_tsv))
    return built


def list_indexed_dictcc_pairs() -> list[tuple[str, str]]:
    """Enumerate the ``(source, target)`` pairs currently cached on disk.

    Used by the Calibre plugin's settings panel to show what the user has
    already ingested without keeping a separate registry.

    Returns:
        Sorted list of ``(source_lang, target_lang)`` tuples derived from
        ``dictcc-<src>-<tgt>.sqlite`` filenames in the cache directory.
    """
    cache = _wiktionary.cache_dir()
    if not cache.is_dir():
        return []
    pairs: list[tuple[str, str]] = []
    for entry in cache.iterdir():
        match = _INDEX_FILE_RE.match(entry.name)
        if entry.is_file() and match:
            pairs.append((match.group(1), match.group(2)))
    return sorted(pairs)


class DictCCDictionary(Dictionary):
    """In-memory dictionary backed by a single dict.cc export file.

    The file is loaded eagerly via :meth:`from_file` and held in a dict mapping
    normalized source lemma to a list of candidate target terms. Prefer
    :class:`DictCCIndex` for repeated runs — it caches the parse to SQLite.
    """

    def __init__(self, source_lang: str, target_lang: str, entries: dict[str, list[str]]) -> None:
        """Construct directly from a prebuilt entries map.

        Prefer :meth:`from_file` for the typical case of loading from disk.

        Args:
            source_lang: Source language code. Lowercased internally.
            target_lang: Target language code. Lowercased internally.
            entries: Map from normalized source lemma to candidate targets.
        """
        self._source_lang = source_lang.lower()
        self._target_lang = target_lang.lower()
        self._entries = entries

    @classmethod
    def from_file(cls, path: Path | str, source_lang: str, target_lang: str) -> DictCCDictionary:
        """Parse a dict.cc export file into an in-memory dictionary.

        Args:
            path: Filesystem path to a tab-separated dict.cc export.
            source_lang: Source language code.
            target_lang: Target language code.

        Returns:
            A populated :class:`DictCCDictionary`.
        """
        entries: dict[str, list[str]] = {}
        for word_norm, translation in iter_dictcc_pairs(path):
            entries.setdefault(word_norm, []).append(translation)
        return cls(source_lang, target_lang, entries)

    def candidates(self, key: LookupKey) -> list[str]:
        """Return candidate translations for ``key``.

        The backend short-circuits (returns ``[]``) when the lookup key's
        language pair does not match this dictionary's direction, so a
        composite of multiple dict.cc files can be used safely.

        Args:
            key: Lookup key. ``key.source_lang`` and ``key.target_lang`` must
                match the direction this dictionary was loaded for.

        Returns:
            All candidate translations (order preserved from the file), or
            ``[]`` if the direction does not match or the lemma is unknown.
        """
        if key.source_lang.lower() != self._source_lang:
            return []
        if key.target_lang.lower() != self._target_lang:
            return []
        return list(self._entries.get(normalize_for_lookup(key.lemma), []))


class DictCCIndex(Dictionary):
    """SQLite-backed dict.cc dictionary for a single language direction.

    Reads from the cache file built by :func:`build_dictcc_index`. The
    connection is opened lazily on first lookup so constructing a backend
    for a non-existent cache file is cheap and silent (the dictionary
    simply returns no candidates).
    """

    def __init__(
        self,
        source_lang: str,
        target_lang: str,
        index_path: Path | None = None,
    ) -> None:
        """Bind the backend to an on-disk cache file.

        Args:
            source_lang: ISO 639-1 source-language code.
            target_lang: ISO 639-1 target-language code.
            index_path: Optional explicit cache path. Defaults to the per-user
                location returned by :func:`dictcc_index_path_for`.
        """
        self._source_lang = source_lang.lower()
        self._target_lang = target_lang.lower()
        self._index_path = index_path or dictcc_index_path_for(source_lang, target_lang)
        self._conn: sqlite3.Connection | None = None

    @property
    def is_available(self) -> bool:
        """Whether the backing SQLite cache file exists."""
        return self._index_path.exists()

    @property
    def index_path(self) -> Path:
        """Filesystem path to the backing SQLite cache (may not yet exist)."""
        return self._index_path

    def _connection(self) -> sqlite3.Connection | None:
        """Open the SQLite connection lazily, or return None if unavailable."""
        if not self.is_available:
            return None
        if self._conn is None:
            self._conn = sqlite3.connect(self._index_path)
        return self._conn

    def candidates(self, key: LookupKey) -> list[str]:
        """Return all cached translations for ``key``.

        Args:
            key: Lookup key. Returns ``[]`` when the language direction does
                not match this index.

        Returns:
            Translations in insertion order (which preserves the original
            TSV file order), or ``[]`` when no entry exists or the cache is
            absent.
        """
        if key.source_lang.lower() != self._source_lang:
            return []
        if key.target_lang.lower() != self._target_lang:
            return []
        conn = self._connection()
        if conn is None:
            return []
        rows = conn.execute(
            "SELECT translation FROM entries WHERE word_norm = ?",
            (normalize_for_lookup(key.lemma),),
        ).fetchall()
        return [row[0] for row in rows]

    def close(self) -> None:
        """Close the underlying SQLite connection, if open."""
        if self._conn is not None:
            self._conn.close()
            self._conn = None
