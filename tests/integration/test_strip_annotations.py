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


def test_strip_restores_original_stylesheets(
    minimal_epub: Path,
    permissive_fr_dict: Dictionary,
    tmp_path: Path,
):
    """Regression: annotate_epub lost original <link> stylesheets because ebooklib
    drops item.links on read_epub. strip_annotations must restore them so the
    stripped EPUB's <head> matches the original rather than being link-free."""
    import zipfile as _zf

    def _css_links(path):
        with _zf.ZipFile(path) as zf:
            hrefs = set()
            for name in zf.namelist():
                if not name.endswith((".xhtml", ".html", ".htm")):
                    continue
                content = zf.read(name).decode("utf-8")
                from bs4 import BeautifulSoup
                soup = BeautifulSoup(content, "lxml-xml")
                for tag in soup.find_all("link"):
                    rel = tag.get("rel", "")
                    if isinstance(rel, list):
                        rel = " ".join(rel)
                    if "stylesheet" in rel.lower():
                        hrefs.add(tag.get("href", ""))
        return hrefs

    original_links = _css_links(minimal_epub)
    assert original_links, "sample EPUB must have at least one stylesheet link"

    annotator = Annotator(
        permissive_fr_dict,
        AnnotationConfig(source_lang="fr", target_lang="en", cutoff=4.5, active_level="B2"),
    )
    annotated = tmp_path / "annotated.epub"
    annotate_epub(minimal_epub, annotated, annotator)

    # Annotated EPUB must preserve the original stylesheets alongside ours.
    annotated_links = _css_links(annotated)
    assert original_links.issubset(annotated_links), (
        f"original CSS links lost during annotation: {original_links - annotated_links}"
    )
    assert any(STYLESHEET_FILENAME in h for h in annotated_links)

    # Stripped EPUB must restore original stylesheets and drop ours.
    stripped = tmp_path / "stripped.epub"
    strip_annotations(annotated, stripped)
    stripped_links = _css_links(stripped)
    assert original_links.issubset(stripped_links), (
        f"original CSS links not restored after strip: {original_links - stripped_links}"
    )
    assert not any(STYLESHEET_FILENAME in h for h in stripped_links), (
        "ell-annotations.css must be gone after strip"
    )


def test_cli_strip_default_output_path(annotated_epub: Path):
    result = CliRunner().invoke(main, ["strip-annotations", str(annotated_epub)])
    assert result.exit_code == 0, result.output
    expected = annotated_epub.with_suffix(".stripped.epub")
    assert expected.exists()
