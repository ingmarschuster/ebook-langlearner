"""End-to-end tests for ``strip-annotations``.

Annotates a sample EPUB then strips it; asserts the prose comes back
clean and the bundled stylesheet/links are gone.
"""

from __future__ import annotations

import zipfile
from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner
from ebooklib import ITEM_DOCUMENT, epub

from ebook_langlearner.annotate import AnnotationConfig, Annotator
from ebook_langlearner.cli import main
from ebook_langlearner.epub_pipeline import (
    STYLESHEET_FILENAME,
    annotate_epub,
    strip_annotations,
)
from ebook_langlearner.render import AnnotationFormat

if TYPE_CHECKING:
    from pathlib import Path

    from ebook_langlearner.dictionaries.base import Dictionary


@pytest.fixture(params=[AnnotationFormat.RUBY, AnnotationFormat.PARENTHETICAL])
def annotated_epub(
    request: pytest.FixtureRequest,
    minimal_epub: Path,
    permissive_fr_dict: Dictionary,
    tmp_path: Path,
) -> Path:
    out = tmp_path / f"annotated.{request.param.value}.epub"
    annotator = Annotator(
        permissive_fr_dict,
        AnnotationConfig(
            source_lang="fr",
            target_lang="en",
            cutoff=4.5,
            fmt=request.param,
            active_level="B2",
        ),
    )
    annotate_epub(minimal_epub, out, annotator)
    return out


def _zip_names(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as zf:
        return zf.namelist()


def _zip_xhtml(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        return "\n".join(
            zf.read(n).decode("utf-8")
            for n in zf.namelist()
            if n.endswith((".xhtml", ".html", ".htm"))
        )


def test_strip_removes_every_annotation(annotated_epub: Path, tmp_path: Path):
    # Sanity: the annotated EPUB actually has annotations to strip.
    assert "ell-annot" in _zip_xhtml(annotated_epub)

    out = tmp_path / "stripped.epub"
    stats = strip_annotations(annotated_epub, out)
    assert stats.annotations_removed > 0

    stripped = _zip_xhtml(out)
    assert "ell-annot" not in stripped
    assert "<ruby" not in stripped
    assert "ell-level-" not in stripped


def test_strip_drops_stylesheet_file_and_links(annotated_epub: Path, tmp_path: Path):
    out = tmp_path / "stripped.epub"
    strip_annotations(annotated_epub, out)
    names = _zip_names(out)
    assert not any(n.endswith(STYLESHEET_FILENAME) for n in names)
    # And the surviving XHTML must not still link to it.
    assert STYLESHEET_FILENAME not in _zip_xhtml(out)


def test_strip_preserves_documents(annotated_epub: Path, tmp_path: Path):
    """Document count survives the strip — we never delete chapters."""
    book_before = epub.read_epub(str(annotated_epub))
    out = tmp_path / "stripped.epub"
    strip_annotations(annotated_epub, out)
    book_after = epub.read_epub(str(out))
    before = sum(1 for _ in book_before.get_items_of_type(ITEM_DOCUMENT))
    after = sum(1 for _ in book_after.get_items_of_type(ITEM_DOCUMENT))
    assert before == after


def test_strip_is_idempotent(annotated_epub: Path, tmp_path: Path):
    once = tmp_path / "once.epub"
    twice = tmp_path / "twice.epub"
    strip_annotations(annotated_epub, once)
    stats_again = strip_annotations(once, twice)
    # Second pass has nothing to remove.
    assert stats_again.annotations_removed == 0
    assert "ell-annot" not in _zip_xhtml(twice)


def test_cli_strip_annotations(annotated_epub: Path, tmp_path: Path):
    out = tmp_path / "stripped.epub"
    result = CliRunner().invoke(
        main, ["strip-annotations", str(annotated_epub), "--output", str(out)]
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert "ell-annot" not in _zip_xhtml(out)


def test_cli_strip_default_output_path(annotated_epub: Path):
    result = CliRunner().invoke(main, ["strip-annotations", str(annotated_epub)])
    assert result.exit_code == 0, result.output
    expected = annotated_epub.with_suffix(".stripped.epub")
    assert expected.exists()
