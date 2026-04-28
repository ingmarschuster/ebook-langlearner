"""End-to-end tests for the ``set-level`` flow.

Annotates a sample EPUB once, then exercises both the Python API
(:func:`epub_pipeline.set_visible_level`) and the CLI (``set-level``)
to confirm the active-level CSS block is rewritten in place and the
rest of the book is untouched.
"""

from __future__ import annotations

import zipfile
from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner

from ebook_langlearner.annotate import AnnotationConfig, Annotator
from ebook_langlearner.cli import main
from ebook_langlearner.epub_pipeline import (
    STYLESHEET_FILENAME,
    MissingStylesheetError,
    annotate_epub,
    get_active_level,
    set_visible_level,
)
from ebook_langlearner.render import (
    BEGIN_LEVEL_MARKER_PREFIX,
    END_LEVEL_MARKER,
    AnnotationFormat,
)

if TYPE_CHECKING:
    from pathlib import Path

    from ebook_langlearner.dictionaries.base import Dictionary


@pytest.fixture
def annotated_epub(
    minimal_epub: Path,
    permissive_fr_dict: Dictionary,
    tmp_path: Path,
) -> Path:
    """Return a freshly-annotated EPUB at default active level B2."""
    out = tmp_path / "annotated.b2.epub"
    annotator = Annotator(
        permissive_fr_dict,
        AnnotationConfig(
            source_lang="fr",
            target_lang="en",
            cutoff=4.5,
            fmt=AnnotationFormat.RUBY,
            active_level="B2",
        ),
    )
    annotate_epub(minimal_epub, out, annotator)
    return out


def _read_stylesheet(path: Path) -> str:
    with zipfile.ZipFile(path) as zf:
        css_name = next(n for n in zf.namelist() if n.endswith(STYLESHEET_FILENAME))
        return zf.read(css_name).decode("utf-8")


def test_set_visible_level_rewrites_only_marker_block(annotated_epub: Path, tmp_path: Path):
    out = tmp_path / "switched.a1.epub"
    set_visible_level(annotated_epub, out, "A1")

    css_before = _read_stylesheet(annotated_epub)
    css_after = _read_stylesheet(out)

    # The base rules outside the marker block must be byte-identical.
    before_base = css_before.split(BEGIN_LEVEL_MARKER_PREFIX, 1)[0]
    after_base = css_after.split(BEGIN_LEVEL_MARKER_PREFIX, 1)[0]
    assert before_base == after_base
    assert f"{BEGIN_LEVEL_MARKER_PREFIX}a1 === */" in css_after
    assert END_LEVEL_MARKER in css_after
    # A1 reveals every level, so all six selectors must be present.
    for level in ("a1", "a2", "b1", "b2", "c1", "c2"):
        assert f".ell-annot.ell-level-{level}" in css_after


def test_set_visible_level_preserves_ruby_font_pct(
    minimal_epub: Path,
    permissive_fr_dict: Dictionary,
    tmp_path: Path,
):
    annotated = tmp_path / "annotated.epub"
    annotate_epub(
        minimal_epub,
        annotated,
        Annotator(
            permissive_fr_dict,
            AnnotationConfig(
                source_lang="fr",
                target_lang="en",
                cutoff=4.5,
                fmt=AnnotationFormat.RUBY,
                ruby_font_pct=72.0,
                active_level="B2",
            ),
        ),
    )
    out = tmp_path / "switched.epub"
    set_visible_level(annotated, out, "C1")
    assert "font-size: 72%" in _read_stylesheet(out)


def test_get_active_level_round_trips(annotated_epub: Path, tmp_path: Path):
    assert get_active_level(annotated_epub) == "B2"
    out = tmp_path / "switched.c1.epub"
    set_visible_level(annotated_epub, out, "c1")
    assert get_active_level(out) == "C1"


def test_set_level_raises_on_unannotated_epub(minimal_epub: Path, tmp_path: Path):
    with pytest.raises(MissingStylesheetError):
        set_visible_level(minimal_epub, tmp_path / "x.epub", "A1")


def test_cli_set_level_writes_output(annotated_epub: Path, tmp_path: Path):
    out = tmp_path / "via-cli.a2.epub"
    result = CliRunner().invoke(
        main,
        ["set-level", str(annotated_epub), "--level", "a2", "--output", str(out)],
    )
    assert result.exit_code == 0, result.output
    assert out.exists()
    assert get_active_level(out) == "A2"


def test_cli_set_level_default_output_path(annotated_epub: Path):
    result = CliRunner().invoke(main, ["set-level", str(annotated_epub), "--level", "C2"])
    assert result.exit_code == 0, result.output
    expected = annotated_epub.with_suffix(".c2.epub")
    assert expected.exists()
    assert get_active_level(expected) == "C2"


def test_cli_set_level_errors_on_unannotated_epub(minimal_epub: Path, tmp_path: Path):
    result = CliRunner().invoke(
        main,
        [
            "set-level",
            str(minimal_epub),
            "--level",
            "A1",
            "--output",
            str(tmp_path / "x.epub"),
        ],
    )
    assert result.exit_code == 2
    assert "cannot switch level" in result.output.lower()
