"""Dictionary backends for ebook-langlearner.

Public exports:

* :class:`Dictionary` — the abstract interface every backend implements.
* :class:`LookupKey` — the immutable lookup request.
* :class:`CompositeDictionary` — chain multiple backends in preference order.
* :class:`DictCCDictionary` — parse a user-supplied dict.cc export file
  into memory ad-hoc.
* :class:`DictCCIndex` — SQLite-cached dict.cc backend for repeat use.
* :class:`WiktionaryDictionary` — SQLite-indexed Wiktionary/Kaikki backend.
"""

from .base import Dictionary, LookupKey
from .composite import CompositeDictionary
from .dictcc import DictCCDictionary, DictCCIndex
from .wiktionary import WiktionaryDictionary

__all__ = [
    "CompositeDictionary",
    "DictCCDictionary",
    "DictCCIndex",
    "Dictionary",
    "LookupKey",
    "WiktionaryDictionary",
]
