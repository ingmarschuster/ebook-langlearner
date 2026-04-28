"""Tests for HTML rendering of annotations."""

from __future__ import annotations

import pytest

from ebook_langlearner.render import (
    BEGIN_LEVEL_MARKER_PREFIX,
    DEFAULT_ACTIVE_LEVEL,
    DEFAULT_RUBY_FONT_PCT,
    END_LEVEL_MARKER,
    AnnotationFormat,
    build_active_level_block,
    build_annotation_css,
    render_translations,
)


def test_ruby_format_wraps_word_and_translations():
    html = render_translations("chat", ["cat", "feline"], AnnotationFormat.RUBY, "ell-level-b1")
    assert html.startswith("<ruby")
    assert "<rt" in html
    assert "chat" in html
    assert "cat/feline" in html
    assert "ell-level-b1" in html


def test_parenthetical_format_uses_split_spans():
    html = render_translations("chat", ["cat"], AnnotationFormat.PARENTHETICAL, "ell-level-a2")
    assert html == (
        '<span class="ell-annot ell-level-a2">chat<span class="ell-trans"> (cat)</span></span>'
    )


def test_empty_translations_return_escaped_word():
    html = render_translations("<b>", [], AnnotationFormat.RUBY, "ell-level-b2")
    assert html == "&lt;b&gt;"


def test_html_special_chars_are_escaped():
    html = render_translations("<b>", ["&amp"], AnnotationFormat.PARENTHETICAL, "ell-level-c1")
    assert html == (
        '<span class="ell-annot ell-level-c1">&lt;b&gt;'
        '<span class="ell-trans"> (&amp;amp)</span></span>'
    )


def test_default_ruby_font_pct_is_below_100():
    assert 50.0 < DEFAULT_RUBY_FONT_PCT < 100.0


def test_build_annotation_css_uses_default_percent():
    css = build_annotation_css()
    assert f"font-size: {DEFAULT_RUBY_FONT_PCT:g}%" in css
    assert "body { line-height: 1.7; }" in css
    assert "line-height: 1" in css


@pytest.mark.parametrize("pct", [50.0, 75.0, 90.0, 100.0, 120.0])
def test_build_annotation_css_renders_arbitrary_percent(pct: float):
    css = build_annotation_css(ruby_font_pct=pct)
    assert f"font-size: {pct:g}%" in css


def test_build_annotation_css_uses_percent_unit_not_calc():
    css = build_annotation_css(ruby_font_pct=85.0)
    assert "calc(" not in css
    assert "%" in css


def test_build_annotation_css_strips_trailing_zero():
    assert "font-size: 90%" in build_annotation_css(ruby_font_pct=90.0)
    assert "font-size: 87.5%" in build_annotation_css(ruby_font_pct=87.5)


def test_build_annotation_css_emits_active_level_markers():
    css = build_annotation_css(active_level="b2")
    begin = f"{BEGIN_LEVEL_MARKER_PREFIX}b2 === */"
    assert begin in css
    assert END_LEVEL_MARKER in css


def test_active_level_a1_reveals_every_level():
    block = build_active_level_block("a1")
    for level in ("a1", "a2", "b1", "b2", "c1", "c2"):
        assert f".ell-annot.ell-level-{level}" in block


def test_active_level_c2_reveals_only_c2():
    block = build_active_level_block("c2")
    assert ".ell-annot.ell-level-c2" in block
    for hidden in ("a1", "a2", "b1", "b2", "c1"):
        assert f".ell-annot.ell-level-{hidden} {{" not in block
        # The selector list also disallows the level appearing as a comma-
        # joined selector — guard with the leading-dot full prefix.
        assert f".ell-annot.ell-level-{hidden}\n" not in block
        assert f".ell-annot.ell-level-{hidden}," not in block


def test_active_level_default_is_b2():
    css = build_annotation_css()
    assert f"{BEGIN_LEVEL_MARKER_PREFIX}{DEFAULT_ACTIVE_LEVEL.lower()} === */" in css


def test_active_level_b1_reveals_b1_b2_c1_c2():
    block = build_active_level_block("b1")
    revealed = ("b1", "b2", "c1", "c2")
    for level in revealed:
        assert f".ell-annot.ell-level-{level}" in block
    for hidden in ("a1", "a2"):
        # Same boundary checks as the C2 case to catch any over-reveal.
        assert f".ell-annot.ell-level-{hidden} {{" not in block
        assert f".ell-annot.ell-level-{hidden}," not in block
        assert f".ell-annot.ell-level-{hidden}\n" not in block


# ── Regression tests for bugs fixed during calibre-plugin development ─────────

def test_active_level_block_does_not_hide_parent_element():
    # Regression: old code set `.ell-annot { display: none }` which hid the
    # annotated word itself, not just its translation.
    block = build_active_level_block("b2")
    assert ".ell-annot { display: none" not in block


def test_active_level_block_ruby_uses_ruby_text_not_inline():
    # Regression: `display: inline` on a <ruby> breaks rt-above-word layout.
    block = build_active_level_block("b2")
    assert "display: ruby-text" in block
    assert "ruby.ell-annot" in block
    assert "rt.ell-rt" in block


def test_active_level_block_targets_child_translation_elements():
    # The block must toggle the child rt / .ell-trans, not the parent wrapper.
    block = build_active_level_block("b2")
    assert "rt.ell-rt" in block
    assert ".ell-trans" in block


def test_annotation_css_hides_rt_by_default_in_static_rules():
    # The static (non-rewritable) part of the CSS must default-hide rt so that
    # hidden-level ruby shows the word but not the translation.
    css = build_annotation_css()
    static = css.split(BEGIN_LEVEL_MARKER_PREFIX)[0]
    assert "rt.ell-rt" in static
    assert "display: none" in static


def test_annotation_css_hides_ell_trans_by_default_in_static_rules():
    css = build_annotation_css()
    static = css.split(BEGIN_LEVEL_MARKER_PREFIX)[0]
    assert ".ell-trans" in static
    assert "display: none" in static


def test_annotation_css_translation_italic_not_word_bold():
    # Regression: old code bolded the annotated word and set translation to
    # normal weight. Correct style: translation in italic, word unstyled.
    css = build_annotation_css()
    assert "font-style: italic" in css
    assert "font-weight: bold" not in css
