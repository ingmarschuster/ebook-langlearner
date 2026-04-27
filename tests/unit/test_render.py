"""Tests for HTML rendering of annotations."""

from __future__ import annotations

import pytest

from ebook_langlearner.render import (
    DEFAULT_RUBY_FONT_PCT,
    AnnotationFormat,
    build_ruby_css,
    render_translations,
)


def test_ruby_format_wraps_word_and_translations():
    html = render_translations("chat", ["cat", "feline"], AnnotationFormat.RUBY)
    assert html.startswith("<ruby")
    assert "<rt" in html
    assert "chat" in html
    assert "cat/feline" in html


def test_parenthetical_format_uses_span():
    html = render_translations("chat", ["cat"], AnnotationFormat.PARENTHETICAL)
    assert html == '<span class="ell-annot">chat (cat)</span>'


def test_empty_translations_return_escaped_word():
    html = render_translations("<b>", [], AnnotationFormat.RUBY)
    assert html == "&lt;b&gt;"


def test_html_special_chars_are_escaped():
    html = render_translations("<b>", ["&amp"], AnnotationFormat.PARENTHETICAL)
    # Both the word and the translation must be escaped exactly once.
    assert html == '<span class="ell-annot">&lt;b&gt; (&amp;amp)</span>'


def test_default_ruby_font_pct_is_below_100():
    # The default must shrink the rt slightly relative to the base word so
    # the annotation is visibly distinct without overpowering the line.
    assert 50.0 < DEFAULT_RUBY_FONT_PCT < 100.0


def test_build_ruby_css_uses_default_percent():
    css = build_ruby_css()
    assert f"font-size: {DEFAULT_RUBY_FONT_PCT:g}%" in css
    # The line-height contagion fix must remain intact.
    assert "body { line-height: 1.7; }" in css
    assert "line-height: 1" in css


@pytest.mark.parametrize("pct", [50.0, 75.0, 90.0, 100.0, 120.0])
def test_build_ruby_css_renders_arbitrary_percent(pct: float):
    css = build_ruby_css(pct)
    assert f"font-size: {pct:g}%" in css


def test_build_ruby_css_uses_percent_unit_not_calc():
    # Pure percent keeps the stylesheet portable across readers (Kindle KF8
    # in particular doesn't reliably support CSS calc()).
    css = build_ruby_css(85.0)
    assert "calc(" not in css
    assert "%" in css


def test_build_ruby_css_strips_trailing_zero():
    # ``:g`` formatting should keep CSS terse: "90%" not "90.0%".
    assert "font-size: 90%" in build_ruby_css(90.0)
    assert "font-size: 87.5%" in build_ruby_css(87.5)
