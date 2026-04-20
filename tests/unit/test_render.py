"""Tests for HTML rendering of annotations."""

from __future__ import annotations

from ebook_langlearner.render import AnnotationFormat, render_translations


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
