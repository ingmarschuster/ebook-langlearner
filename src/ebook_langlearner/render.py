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


RUBY_CSS = """
body { line-height: 1.7; }
ruby.ell-annot { ruby-align: center; }
ruby.ell-annot rt.ell-rt { font-size: 0.55em; opacity: 0.75; line-height: 1; }
span.ell-annot { }
""".strip()
"""CSS injected into annotated EPUBs to size and style the ruby annotations.

The ``body { line-height: 1.7 }`` reserves vertical room for every line so the
rt annotation can sit above without expanding any line-box. The
``rt { line-height: 1 }`` prevents the rt's own line-height from contributing
to its parent's line-box height — without it, readers like Calibre
(QtWebEngine) and Kindle KF8 promote the whole paragraph's line-box to fit
the rt, which visibly spreads *ruby-less* neighbouring lines apart.
"""
