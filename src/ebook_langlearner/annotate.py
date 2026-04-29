"""Text-node annotation.

Given a chunk of plain text (extracted from a single XHTML text node), this
module produces an HTML fragment in which every rare word is wrapped with a
translation annotation and every other character (punctuation, whitespace,
common words, proper nouns, numbers) is preserved verbatim but HTML-escaped.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape

from .cefr import level_class, level_for_zipf
from .dictionaries.base import Dictionary, LookupKey, rank_candidates
from .frequency import zipf
from .lemma_frequency import lemma_zipf
from .lemmatize import lemmatize
from .render import (
    DEFAULT_ACTIVE_LEVEL,
    DEFAULT_ANNOTATION_GREY_PCT,
    DEFAULT_RUBY_FONT_PCT,
    AnnotationFormat,
    render_translations,
)
from .tokenize import (
    SENTENCE_END,
    Token,
    is_numeric,
    is_too_short,
    looks_like_proper_noun,
    normalize_for_lookup,
    tokenize,
)


@dataclass(frozen=True)
class AnnotationConfig:
    """Configuration for :class:`Annotator`.

    Attributes:
        source_lang: ISO 639-1 code of the text's language.
        target_lang: ISO 639-1 code of the translation language.
        cutoff: Zipf frequency cutoff; words strictly below this are
            considered for annotation. Typical useful range is 2.5 to 5.5.
            Independent of ``active_level``: lowering the cutoff narrows
            *which* words get tagged at all, while ``active_level`` only
            controls which already-tagged annotations are visible.
        fmt: HTML annotation format. Defaults to ``RUBY``.
        max_translations: Maximum candidates per annotated word. Defaults to 2
            (rendered as ``a/b``).
        min_word_length: Words shorter than this are skipped (never annotated).
        ruby_font_pct: Ruby translation font-size as a percentage of the
            base word's font-size. Only consulted when ``fmt`` is
            :attr:`AnnotationFormat.RUBY`. See
            :func:`render.build_annotation_css`.
        active_level: CEFR level whose annotations are visible by default in
            the produced EPUB. Words below the cutoff are tagged regardless;
            this only affects the initial CSS gate. Switch later with the
            ``set-level`` CLI command.
    """

    source_lang: str
    target_lang: str
    cutoff: float
    fmt: AnnotationFormat = AnnotationFormat.RUBY
    max_translations: int = 2
    min_word_length: int = 2
    ruby_font_pct: float = DEFAULT_RUBY_FONT_PCT
    annotation_grey_pct: float = DEFAULT_ANNOTATION_GREY_PCT
    active_level: str = DEFAULT_ACTIVE_LEVEL


class Annotator:
    """Annotate plain text with inline translations for rare words.

    This class is pure and stateless apart from the dictionary it was
    constructed with; the same instance may be used concurrently across
    multiple EPUB documents.
    """

    def __init__(self, dictionary: Dictionary, config: AnnotationConfig) -> None:
        """Build an annotator.

        Args:
            dictionary: Dictionary backend used for lookups. Pass a
                :class:`~ebook_langlearner.dictionaries.composite.CompositeDictionary`
                to chain several backends.
            config: Annotation configuration.
        """
        self._dict = dictionary
        self._cfg = config

    @property
    def config(self) -> AnnotationConfig:
        """Return the immutable :class:`AnnotationConfig` this annotator was built with."""
        return self._cfg

    def annotate_text(self, text: str) -> str:
        """Annotate a plain-text string.

        Rare words are replaced with an HTML fragment from :func:`render_translations`;
        all other characters are HTML-escaped. The returned fragment preserves
        original whitespace and punctuation exactly.

        Args:
            text: The plain text of a single XHTML text node. Must not contain
                HTML markup (the EPUB pipeline ensures this).

        Returns:
            An HTML fragment safe to insert in place of ``text``.
        """
        tokens = tokenize(text)
        out: list[str] = []
        prev_nonword = ""
        for token in tokens:
            if not token.is_word:
                prev_nonword = token.text
                out.append(escape(token.text))
                continue
            out.append(self._render_word(token, prev_nonword))
            prev_nonword = ""
        return "".join(out)

    def _render_word(self, token: Token, prev_nonword: str) -> str:
        """Decide whether ``token`` is rare and render it accordingly.

        Delegates to :meth:`_translations_for` for the filter cascade;
        returns the escaped original word whenever that cascade declines to
        produce a translation list.
        """
        result = self._translations_for(token, prev_nonword)
        if result is None:
            return escape(token.text)
        translations, lemma_z = result
        level = level_for_zipf(self._cfg.source_lang, lemma_z)
        if level is None:
            return escape(token.text)
        return render_translations(token.text, translations, self._cfg.fmt, level_class(level))

    def _translations_for(self, token: Token, prev_nonword: str) -> tuple[list[str], float] | None:
        """Run the rare-word filter cascade and return ranked translations.

        Cascade (short-circuiting, cheapest first): length → numeric →
        proper noun → surface-form frequency → lemma-aggregated frequency →
        dictionary hit. The surface-form gate catches very common inflected
        forms regardless of how the lemmatizer resolves them; the
        lemma-aggregate gate uses precomputed sums over every inflection of
        a lemma (via :func:`lemma_zipf`) so that e.g. "manger" with
        aggregate Zipf ~5.3 is recognized as common even though its
        infinitive form alone only scores ~5.0.

        Returns:
            ``(translations, lemma_zipf)`` for words that pass the cascade,
            or ``None`` when the token should be left untouched. The lemma
            Zipf is returned so the caller can map it to a CEFR class.
        """
        word = token.text
        if is_too_short(word, min_length=self._cfg.min_word_length):
            return None
        if is_numeric(word):
            return None
        if looks_like_proper_noun(word, sentence_start=_is_sentence_start(prev_nonword)):
            return None
        surface = normalize_for_lookup(word)
        if zipf(surface, self._cfg.source_lang) >= self._cfg.cutoff:
            return None
        lemma = lemmatize(surface, self._cfg.source_lang)
        lemma_z = lemma_zipf(lemma, self._cfg.source_lang)
        if lemma_z >= self._cfg.cutoff:
            return None
        key = LookupKey(
            lemma=lemma,
            source_lang=self._cfg.source_lang,
            target_lang=self._cfg.target_lang,
        )
        translations = rank_candidates(
            self._dict.candidates(key),
            target_lang=self._cfg.target_lang,
            limit=self._cfg.max_translations,
        )
        return (translations, lemma_z) if translations else None


def _is_sentence_start(prev_nonword: str) -> bool:
    """Return ``True`` if the trailing non-word run indicates a sentence start.

    Whitespace-only runs are treated as mid-sentence to avoid false positives:
    a capitalized word after a space should be recognized as a proper noun,
    not as the start of a sentence.
    """
    if not prev_nonword:
        return True
    stripped = prev_nonword.rstrip()
    if not stripped:
        return False
    return stripped[-1] in SENTENCE_END
