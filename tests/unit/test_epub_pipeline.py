"""Unit tests for epub_pipeline helpers."""

from __future__ import annotations

from ebooklib import epub

from ebook_langlearner.epub_pipeline import STYLESHEET_FILENAME, _register_stylesheet_link


def _make_item(file_name: str) -> epub.EpubHtml:
    item = epub.EpubHtml()
    item.file_name = file_name
    return item


def test_register_stylesheet_link_root_item_uses_plain_filename():
    # Item at root level: href should be just the filename, no ../
    item = _make_item("chapter.xhtml")
    _register_stylesheet_link(item)
    hrefs = [lnk.get("href") for lnk in item.links]
    assert STYLESHEET_FILENAME in hrefs


def test_register_stylesheet_link_subdir_item_uses_relative_path():
    # Regression: items in subdirectories got href="ell-annotations.css" which
    # resolves relative to the file's own directory, missing the stylesheet.
    item = _make_item("text/chapter.xhtml")
    _register_stylesheet_link(item)
    hrefs = [lnk.get("href") for lnk in item.links]
    assert f"../{STYLESHEET_FILENAME}" in hrefs


def test_register_stylesheet_link_deep_subdir_uses_correct_depth():
    item = _make_item("a/b/chapter.xhtml")
    _register_stylesheet_link(item)
    hrefs = [lnk.get("href") for lnk in item.links]
    assert f"../../{STYLESHEET_FILENAME}" in hrefs


def test_register_stylesheet_link_idempotent():
    item = _make_item("text/chapter.xhtml")
    _register_stylesheet_link(item)
    _register_stylesheet_link(item)
    hrefs = [lnk.get("href") for lnk in item.links]
    assert hrefs.count(f"../{STYLESHEET_FILENAME}") == 1
