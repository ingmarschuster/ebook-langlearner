"""Parser for dict.cc tab-separated export files.

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

Each export covers a single language direction. Combine multiple exports via
:class:`~ebook_langlearner.dictionaries.composite.CompositeDictionary`.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import TYPE_CHECKING

from ebook_langlearner.tokenize import normalize_for_lookup

from .base import Dictionary

if TYPE_CHECKING:
    from .base import LookupKey

_ANNOTATION_RE = re.compile(r"\s*[\[\{<][^\]\}>]*[\]\}>]\s*")
_PAREN_RE = re.compile(r"\s*\([^)]*\)\s*")

_MIN_FIELDS_PER_LINE = 2


def _clean(term: str) -> str:
    """Remove bracketed and parenthetical annotations and collapse whitespace."""
    term = _ANNOTATION_RE.sub(" ", term)
    term = _PAREN_RE.sub(" ", term)
    return " ".join(term.split())


class DictCCDictionary(Dictionary):
    """In-memory dictionary backed by a single dict.cc export file.

    The file is loaded eagerly via :meth:`from_file` and held in a dict mapping
    normalized source lemma to a list of candidate target terms.
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
        """Parse a dict.cc export file into a dictionary.

        Lines beginning with ``#`` and blank lines are ignored. Malformed lines
        (fewer than two tab-separated fields) are silently skipped; parsing
        does not fail on a single bad line because dict.cc exports occasionally
        contain these.

        Args:
            path: Filesystem path to a tab-separated dict.cc export.
            source_lang: Source language code.
            target_lang: Target language code.

        Returns:
            A populated :class:`DictCCDictionary`.
        """
        entries: dict[str, list[str]] = {}
        with Path(path).open(encoding="utf-8") as fh:
            for raw in fh:
                line = raw.rstrip("\n")
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                if len(parts) < _MIN_FIELDS_PER_LINE:
                    continue
                src, tgt = parts[0], parts[1]
                src_clean = _clean(src)
                tgt_clean = _clean(tgt)
                if not src_clean or not tgt_clean:
                    continue
                key = normalize_for_lookup(src_clean)
                entries.setdefault(key, []).append(tgt_clean)
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
