"""HTML rendering of word + translation annotations.

Two rendering styles are supported:

* **Ruby** (default): ``<ruby>word<rt>translation</rt></ruby>``. Most EPUB3
  readers render this as small text above the base word, similar to furigana.
* **Parenthetical**: ``word (translation)`` wrapped in a span. Always works on
  every reader, at the cost of inline verbosity.

Every annotation is tagged with a ``ell-level-{a1..c2}`` class so a single
CSS-block edit can later show or hide annotations per CEFR level without
re-running the pipeline. See :func:`build_annotation_css` for the rewrite-
target block bracketed by :data:`BEGIN_LEVEL_MARKER` and :data:`END_LEVEL_MARKER`.
"""

from __future__ import annotations

from enum import Enum
from html import escape

from .cefr import levels_revealed_at, normalize_level


class AnnotationFormat(str, Enum):
    """Visual format for annotations inserted into the EPUB."""

    RUBY = "ruby"
    """``<ruby>...<rt>...</rt></ruby>`` — EPUB3 reader-friendly, default."""

    PARENTHETICAL = "parenthetical"
    """``word (translation)`` in a span — works on any reader."""


def render_translations(
    word: str,
    translations: list[str],
    fmt: AnnotationFormat,
    level_cls: str,
) -> str:
    """Render one annotated word as an HTML fragment.

    The input ``word`` and ``translations`` are always HTML-escaped. When
    ``translations`` is empty the word is returned escaped but unwrapped,
    letting callers fall back gracefully.

    Args:
        word: The raw (unescaped) source word to wrap.
        translations: One or more target-language translations (already ranked
            and limited; this function just joins them).
        fmt: Which annotation format to use.
        level_cls: The ``ell-level-{lvl}`` CSS class identifying the CEFR
            level that "owns" this word; used by the active-level CSS block
            to show or hide annotations at runtime.

    Returns:
        An HTML fragment: ``<ruby>...</ruby>`` for
        :attr:`AnnotationFormat.RUBY`, ``<span>word<span>...</span></span>``
        for :attr:`AnnotationFormat.PARENTHETICAL`, or the bare escaped word
        when ``translations`` is empty.
    """
    if not translations:
        return escape(word)
    joined = "/".join(escape(t) for t in translations)
    safe_word = escape(word)
    if fmt is AnnotationFormat.RUBY:
        return (
            f'<ruby class="ell-annot {level_cls}">{safe_word}'
            f'<rt class="ell-rt">{joined}</rt></ruby>'
        )
    # Parenthetical splits into outer + inner span so the parens can be
    # toggled or stripped via CSS without losing the base word.
    return (
        f'<span class="ell-annot {level_cls}">{safe_word}'
        f'<span class="ell-trans"> ({joined})</span></span>'
    )


DEFAULT_RUBY_FONT_PCT = 90.0
"""Default ruby translation font-size, as a percentage of the base word's font-size.

90% renders the rt slightly smaller than the surrounding word — visible
enough to read, distinct enough to skim past when not needed. Pure
percent (rather than ``calc(1em - Npt)``) keeps the stylesheet portable
across readers without depending on CSS ``calc()`` support.
"""

DEFAULT_ACTIVE_LEVEL = "B2"
"""Default visible CEFR level baked into freshly-built annotation CSS."""

BEGIN_LEVEL_MARKER_PREFIX = "/* === BEGIN ELL ACTIVE LEVEL: "
"""Prefix of the marker line introducing the rewrite-target block."""

BEGIN_LEVEL_MARKER_SUFFIX = " === */"
"""Suffix shared by both the BEGIN and END marker lines."""

END_LEVEL_MARKER = "/* === END ELL ACTIVE LEVEL === */"
"""Sentinel line closing the rewrite-target block."""


def _begin_level_marker(level: str) -> str:
    """Return the BEGIN marker line for ``level`` (lowercase)."""
    return f"{BEGIN_LEVEL_MARKER_PREFIX}{level.lower()}{BEGIN_LEVEL_MARKER_SUFFIX}"


def build_active_level_block(active_level: str) -> str:
    """Return the rewrite-target CSS block for ``active_level``.

    The block hides every annotation by default and re-enables only the
    levels at or below ``active_level`` in CEFR proficiency (i.e. the
    level itself plus rarer ones). It is bracketed by
    :data:`BEGIN_LEVEL_MARKER_PREFIX`/:data:`END_LEVEL_MARKER` so that
    :func:`epub_pipeline.set_visible_level` can rewrite it in place.
    """
    level = normalize_level(active_level)
    revealed = levels_revealed_at(level)
    selectors = ",\n".join(f".ell-annot.ell-level-{lvl.lower()}" for lvl in revealed)
    return (
        f"{_begin_level_marker(level)}\n"
        ".ell-annot { display: none; }\n"
        f"{selectors} {{ display: inline; }}\n"
        ".ell-annot .ell-trans { display: inline; }\n"
        f"{END_LEVEL_MARKER}"
    )


def build_annotation_css(
    *,
    ruby_font_pct: float = DEFAULT_RUBY_FONT_PCT,
    active_level: str = DEFAULT_ACTIVE_LEVEL,
) -> str:
    """Build the annotation stylesheet, sized for ruby and gated by CEFR level.

    Args:
        ruby_font_pct: Ruby translation font-size as a percentage of the
            base word's font-size. ``100.0`` keeps the rt the same size;
            below ~50 the rt becomes hard to read, above ~120 it dwarfs
            the base word.
        active_level: CEFR level whose annotations (and any rarer level's
            annotations) should be visible. Switching levels later is a
            one-block edit; see :func:`build_active_level_block`.

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
    base = (
        "body { line-height: 1.7; }\n"
        "ruby.ell-annot { ruby-align: center; }\n"
        f"ruby.ell-annot rt.ell-rt {{ font-size: {pct_value}; "
        "opacity: 0.75; line-height: 1; }\n"
        "span.ell-annot { }\n"
    )
    return base + build_active_level_block(active_level) + "\n"
