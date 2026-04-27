"""End-to-end CLI tests using Click's :class:`CliRunner`.

The CLI is the primary user surface, so smoke-test that user-visible options
(``--ruby-font-pct`` here) round-trip into the produced EPUB rather than
silently being dropped on the floor.
"""

from __future__ import annotations

import zipfile
from typing import TYPE_CHECKING

from click.testing import CliRunner

from ebook_langlearner.cli import main
from ebook_langlearner.epub_pipeline import STYLESHEET_FILENAME

if TYPE_CHECKING:
    from pathlib import Path


def test_annotate_ruby_font_pct_flows_to_stylesheet(
    minimal_epub: Path,
    tiny_dictcc_file: Path,
    tmp_path: Path,
):
    output = tmp_path / "out.epub"
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "annotate",
            str(minimal_epub),
            "--from",
            "fr",
            "--to",
            "en",
            "--cutoff",
            "3.5",
            "--dictcc",
            str(tiny_dictcc_file),
            "--ruby-font-pct",
            "65",
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    assert output.exists()

    with zipfile.ZipFile(output) as zf:
        css_names = [n for n in zf.namelist() if n.endswith(STYLESHEET_FILENAME)]
        assert css_names, "stylesheet must be present in the output"
        css = zf.read(css_names[0]).decode("utf-8")
    assert "font-size: 65%" in css


def test_annotate_default_ruby_font_pct_is_90(
    minimal_epub: Path,
    tiny_dictcc_file: Path,
    tmp_path: Path,
):
    output = tmp_path / "out.epub"
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "annotate",
            str(minimal_epub),
            "--from",
            "fr",
            "--to",
            "en",
            "--cutoff",
            "3.5",
            "--dictcc",
            str(tiny_dictcc_file),
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output

    with zipfile.ZipFile(output) as zf:
        css = zf.read(next(n for n in zf.namelist() if n.endswith(STYLESHEET_FILENAME))).decode(
            "utf-8"
        )
    assert "font-size: 90%" in css


def test_annotate_rejects_out_of_range_pct(
    minimal_epub: Path,
    tiny_dictcc_file: Path,
    tmp_path: Path,
):
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "annotate",
            str(minimal_epub),
            "--from",
            "fr",
            "--to",
            "en",
            "--cutoff",
            "3.5",
            "--dictcc",
            str(tiny_dictcc_file),
            "--ruby-font-pct",
            "10",
            "--output",
            str(tmp_path / "out.epub"),
        ],
    )
    # Click's FloatRange returns exit code 2 for out-of-range values.
    assert result.exit_code == 2
    assert "ruby-font-pct" in result.output.lower() or "10" in result.output
