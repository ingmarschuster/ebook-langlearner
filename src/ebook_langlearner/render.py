"""HTML rendering of word + translation annotations.

Two rendering styles are supported:

* **Ruby** (default): ``<ruby>word<rt>translation</rt></ruby>``. Most EPUB3
  readers render this as small text above the base word, similar to furigana.
* **Parenthetical**: ``word (translation)`` wrapped in a span. Always works on
  every reader, at the cost of inline verbosity.
"""

from __future__ import annotations

from enum import Enum
from html import escape


class AnnotationFormat(str, Enum):
    """Visual format for annotations inserted into the EPUB."""

    RUBY = "ruby"
    """``<ruby>...<rt>...</rt></ruby>`` — EPUB3 reader-friendly, default."""

    PARENTHETICAL = "parenthetical"
    """``word (translation)`` in a span — works on any reader."""


def render_translations(word: str, translations: list[str], fmt: AnnotationFormat) -> str:
    """Render one annotated word as an HTML fragment.

    The input ``word`` and ``translations`` are always HTML-escaped. When
    ``translations`` is empty the word is returned escaped but unwrapped,
    letting callers fall back gracefully.

    Args:
        word: The raw (unescaped) source word to wrap.
        translations: One or more target-language translations (already ranked
            and limited; this function just joins them).
        fmt: Which annotation format to use.

    Returns:
        An HTML fragment: ``<ruby>...</ruby>`` for
        :attr:`AnnotationFormat.RUBY`, ``<span>word (a/b)</span>`` for
        :attr:`AnnotationFormat.PARENTHETICAL`, or the bare escaped word when
        ``translations`` is empty.
    """
    if not translations:
        return escape(word)
    joined = "/".join(escape(t) for t in translations)
    safe_word = escape(word)
    if fmt is AnnotationFormat.RUBY:
        return f'<ruby class="ell-annot">{safe_word}<rt class="ell-rt">{joined}</rt></ruby>'
    return f'<span class="ell-annot">{safe_word} ({joined})</span>'


DEFAULT_RUBY_FONT_PCT = 90.0
"""Default ruby translation font-size, as a percentage of the base word's font-size.

90% renders the rt slightly smaller than the surrounding word — visible
enough to read, distinct enough to skim past when not needed. Pure
percent (rather than ``calc(1em - Npt)``) keeps the stylesheet portable
across readers without depending on CSS ``calc()`` support.
"""


def build_ruby_css(ruby_font_pct: float = DEFAULT_RUBY_FONT_PCT) -> str:
    """Build the annotation stylesheet, sizing the rt relative to the base.

    Args:
        ruby_font_pct: Ruby translation font-size as a percentage of the
            base word's font-size. ``100.0`` keeps the rt the same size;
            below ~50 the rt becomes hard to read, above ~120 it dwarfs
            the base word.

    Returns:
        A self-contained CSS string suitable for shipping inside an EPUB.

    The ``body { line-height: 1.7 }`` reserves vertical room for every line
    so the rt annotation can sit above without expanding any line-box. The
    ``rt { line-height: 1 }`` prevents the rt's own line-height from
    contributing to its parent's line-box height — without it, readers like
    Calibre (QtWebEngine) and Kindle KF8 promote the whole paragraph's
    line-box to fit the rt, which visibly spreads *ruby-less* neighbouring
    lines apart.
    """
    pct_value = f"{ruby_font_pct:g}%"
    return (
        "body { line-height: 1.7; }\n"
        "ruby.ell-annot { ruby-align: center; }\n"
        f"ruby.ell-annot rt.ell-rt {{ font-size: {pct_value}; "
        "opacity: 0.75; line-height: 1; }\n"
        "span.ell-annot { }"
    )
