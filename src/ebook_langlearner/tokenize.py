"""Unicode-aware tokenization and word-classification heuristics.

Tokenization preserves both word and non-word regions so that annotators can
rebuild the original text byte-for-byte while wrapping individual words. The
classifiers (:func:`looks_like_proper_noun`, :func:`is_numeric`,
:func:`is_too_short`) decide which words to skip before frequency lookup.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass

WORD_RE = re.compile(r"[\w\-]+", re.UNICODE)
"""Regex matching a "word" — letters, digits, and internal hyphens.

Hyphens are included so forms like ``peut-être`` survive as a single token.
Apostrophes (straight or typographic) act as separators: in French this
correctly splits elisions such as ``l'arbre`` into ``l`` + ``arbre``, which
matches how lemmatizers and dictionaries key their entries. For English
contractions this is imperfect (``don't`` splits into ``don`` + ``t``), but
the short ``t`` token is filtered out and annotating ``don`` is harmless.
"""


@dataclass(frozen=True)
class Token:
    """A single token carrying its position in the original text.

    Attributes:
        text: The substring exactly as it appeared in the source text.
        start: Inclusive character offset into the original string.
        end: Exclusive character offset into the original string.
    """

    text: str
    start: int
    end: int

    @property
    def is_word(self) -> bool:
        """Whether this token contains at least one alphabetic character."""
        return any(ch.isalpha() for ch in self.text)


def tokenize(text: str) -> list[Token]:
    """Split text into a gap-free sequence of word and non-word tokens.

    The resulting list fully covers the input: concatenating ``token.text`` for
    all tokens reproduces the original string exactly. This lets callers
    reconstruct surrounding whitespace and punctuation when rendering.

    Args:
        text: Arbitrary text to split (may include any Unicode).

    Returns:
        Tokens in input order. Non-word runs (spaces, punctuation) appear as
        their own tokens alongside word tokens.
    """
    tokens: list[Token] = []
    cursor = 0
    for match in WORD_RE.finditer(text):
        start, end = match.span()
        if start > cursor:
            tokens.append(Token(text[cursor:start], cursor, start))
        tokens.append(Token(match.group(), start, end))
        cursor = end
    if cursor < len(text):
        tokens.append(Token(text[cursor:], cursor, len(text)))
    return tokens


def looks_like_proper_noun(word: str, *, sentence_start: bool) -> bool:
    """Heuristically detect a proper noun based on capitalization.

    A capitalized word that is not at the start of a sentence is treated as a
    proper noun so that personal names and place names are not annotated. Words
    at a sentence start are ambiguous and treated as non-proper.

    Args:
        word: The surface form as it appeared in the text.
        sentence_start: ``True`` if the word is the first word of a sentence.

    Returns:
        ``True`` if the word's first cased character is uppercase and
        ``sentence_start`` is ``False``.
    """
    if sentence_start:
        return False
    for ch in word:
        if ch.isalpha():
            return ch.isupper()
    return False


def is_numeric(word: str) -> bool:
    """Return ``True`` if ``word`` contains any digit.

    A mixed token like ``"3rd"`` is considered numeric so we skip it.
    """
    return any(ch.isdigit() for ch in word)


def is_too_short(word: str, *, min_length: int = 2) -> bool:
    """Return ``True`` if ``word`` has fewer than ``min_length`` characters.

    Single-letter words are rarely worth annotating (articles, interjections).
    """
    return len(word) < min_length


def normalize_for_lookup(word: str) -> str:
    """Lowercase and NFC-normalize a word for dictionary key comparison.

    Wiktionary and dict.cc exports store terms in a consistent Unicode form;
    normalizing both sides to NFC avoids false-misses caused by differently
    composed accented characters.

    Args:
        word: The surface form or lemma to normalize.

    Returns:
        The lowercased, NFC-composed word.
    """
    return unicodedata.normalize("NFC", word).lower()


SENTENCE_END = frozenset(".!?…")
"""Characters that close a sentence for the purpose of capitalization analysis."""


def is_sentence_boundary(prev_text: str) -> bool:
    """Decide whether the trailing non-word run ends a sentence.

    The annotator uses this so that capitalized words appearing after a period
    are recognized as sentence-initial (and therefore not treated as proper
    nouns solely because of their capitalization).

    Args:
        prev_text: The concatenation of non-word characters immediately
            preceding the word under consideration. An empty string indicates
            the very start of the input (which is a sentence boundary). A
            whitespace-only run indicates we are inside a sentence (which is
            not a boundary).

    Returns:
        ``True`` if ``prev_text`` is empty or ends with a sentence-terminating
        punctuation mark. ``False`` for whitespace-only or punctuation that
        does not close a sentence.
    """
    if not prev_text:
        return True
    stripped = prev_text.rstrip()
    if not stripped:
        return False
    return stripped[-1] in SENTENCE_END
