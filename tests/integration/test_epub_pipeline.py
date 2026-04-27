"""End-to-end test that runs the EPUB pipeline on the Candide sample."""

from __future__ import annotations

import zipfile
from typing import TYPE_CHECKING

import pytest
from ebooklib import ITEM_DOCUMENT, epub

from ebook_langlearner.annotate import AnnotationConfig, Annotator
from ebook_langlearner.epub_pipeline import (
    STYLESHEET_FILENAME,
    PipelineStats,
    annotate_epub,
)
from ebook_langlearner.render import AnnotationFormat

if TYPE_CHECKING:
    from pathlib import Path

    from ebook_langlearner.dictionaries.base import Dictionary


@pytest.fixture
def annotator_fr_en(permissive_fr_dict: Dictionary) -> Annotator:
    """Annotator with a permissive dict so every rare word gets wrapped."""
    return Annotator(
        permissive_fr_dict,
        AnnotationConfig(
            source_lang="fr",
            target_lang="en",
            cutoff=3.5,
            fmt=AnnotationFormat.RUBY,
        ),
    )


def test_annotate_epub_writes_valid_book_with_ruby(
    minimal_epub: Path,
    annotator_fr_en: Annotator,
    tmp_path: Path,
):
    out_path = tmp_path / "annotated.epub"
    stats = annotate_epub(minimal_epub, out_path, annotator_fr_en)
    assert isinstance(stats, PipelineStats)
    assert stats.documents_processed >= 1
    # Candide is rich enough that at least one rare word per common cutoff
    # must trigger an annotation when using the tiny FR→EN dict.cc fixture.
    assert stats.text_nodes_processed >= 1
    assert out_path.exists()

    book = epub.read_epub(str(out_path))
    chapters = [
        item.get_content().decode("utf-8") for item in book.get_items_of_type(ITEM_DOCUMENT)
    ]
    joined = "\n".join(chapters)
    assert "<ruby" in joined


def test_stylesheet_is_added_and_linked(
    minimal_epub: Path,
    annotator_fr_en: Annotator,
    tmp_path: Path,
):
    out_path = tmp_path / "annotated.epub"
    annotate_epub(minimal_epub, out_path, annotator_fr_en)

    # The CSS file must be present as a zip entry — that's the actual asset
    # EPUB readers look for. Inspect the zip directly rather than relying on
    # ebooklib's round-trip semantics, which rebuild head/body on read.
    with zipfile.ZipFile(out_path) as zf:
        names = zf.namelist()
        assert any(n.endswith(STYLESHEET_FILENAME) for n in names), (
            "stylesheet file must be added to the EPUB"
        )
        chapter_htmls = [
            zf.read(n).decode("utf-8") for n in names if n.endswith((".html", ".xhtml", ".htm"))
        ]

    assert any(STYLESHEET_FILENAME in c for c in chapter_htmls), (
        "at least one chapter must reference the annotation stylesheet"
    )


def test_custom_ruby_font_pct_propagates_to_stylesheet(
    minimal_epub: Path,
    permissive_fr_dict: Dictionary,
    tmp_path: Path,
):
    """A non-default ``ruby_font_pct`` must surface in the bundled CSS file."""
    annotator = Annotator(
        permissive_fr_dict,
        AnnotationConfig(
            source_lang="fr",
            target_lang="en",
            cutoff=3.5,
            fmt=AnnotationFormat.RUBY,
            ruby_font_pct=72.0,
        ),
    )
    out_path = tmp_path / "annotated.epub"
    annotate_epub(minimal_epub, out_path, annotator)

    with zipfile.ZipFile(out_path) as zf:
        css_names = [n for n in zf.namelist() if n.endswith(STYLESHEET_FILENAME)]
        assert css_names, "stylesheet must be present"
        css = zf.read(css_names[0]).decode("utf-8")

    assert "font-size: 72%" in css
    assert "font-size: 90%" not in css
