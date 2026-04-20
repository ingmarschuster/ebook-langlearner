"""Command-line interface for ebook-langlearner.

Subcommands:

* ``languages``               — list supported language codes.
* ``build-wiktionary-index``  — convert a Kaikki JSONL dump into a SQLite index.
* ``annotate``                — annotate an EPUB using configured dictionaries.

Invoke as ``ebook-langlearner <subcommand> ...`` once the package is installed.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

import click

from .annotate import AnnotationConfig, Annotator
from .cefr import CEFR_LEVELS, cefr_cutoff
from .dictionaries import (
    CompositeDictionary,
    DictCCDictionary,
    WiktionaryDictionary,
)
from .dictionaries.wiktionary import build_index
from .epub_pipeline import annotate_epub
from .languages import CORE_LANGUAGES, require_supported
from .render import AnnotationFormat

if TYPE_CHECKING:
    from .dictionaries.base import Dictionary


@click.group()
def main() -> None:
    """Annotate rare words in EPUB files with translations."""


@main.command("languages")
def cmd_languages() -> None:
    """Print the table of supported language codes to stdout."""
    for code, name in sorted(CORE_LANGUAGES.items()):
        click.echo(f"{code}\t{name}")


@main.command("build-wiktionary-index")
@click.option(
    "--source",
    "-s",
    required=True,
    help="Source language code (e.g. fr). Run 'languages' to list supported codes. Run 'languages' to list supported codes.",
)
@click.argument("jsonl", type=click.Path(exists=True, path_type=Path))
def cmd_build_wiktionary_index(source: str, jsonl: Path) -> None:
    """Build a SQLite index from a Kaikki.org JSONL dump for the given source language.

    Download the language's "Sense-disambiguated translations" JSONL from
    https://kaikki.org/dictionary/ and pass the file path as JSONL. The
    resulting index is cached under the user's data directory and picked up
    automatically by 'annotate' when no --dictcc backend matches.
    """
    source = require_supported(source)
    out = build_index(source, jsonl)
    click.echo(f"Built index: {out}")


@main.command("annotate")
@click.argument("input_epub", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--from",
    "source",
    required=True,
    help="Source language code (e.g. fr). Run 'languages' to list supported codes.",
)
@click.option(
    "--to",
    "target",
    required=True,
    help="Target language code (e.g. de). Run 'languages' to list supported codes.",
)
@click.option(
    "--cutoff",
    type=float,
    default=None,
    help=(
        "Zipf-frequency cutoff: words below this are annotated. "
        "Mutually exclusive with --level; defaults to 3.0 if neither is given."
    ),
)
@click.option(
    "--level",
    type=click.Choice(CEFR_LEVELS, case_sensitive=False),
    default=None,
    help="CEFR level of the reader; derives a per-language cutoff. "
    "Mutually exclusive with --cutoff.",
)
@click.option(
    "--format",
    "fmt",
    type=click.Choice(["ruby", "parenthetical"]),
    default="ruby",
    show_default=True,
)
@click.option(
    "--dictcc",
    "dictcc_paths",
    multiple=True,
    type=click.Path(exists=True, path_type=Path),
    help="Path to a dict.cc tab-separated export. Can be passed multiple times.",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output EPUB path. Defaults to <input>.annotated.epub.",
)
def cmd_annotate(
    input_epub: Path,
    source: str,
    target: str,
    cutoff: float | None,
    level: str | None,
    fmt: str,
    dictcc_paths: tuple[Path, ...],
    output: Path | None,
) -> None:
    """Annotate an EPUB using the selected dictionary backends.

    dict.cc backends (one per ``--dictcc`` flag) are consulted first, in the
    order given. If none of them has a hit, the Wiktionary index for ``source``
    is tried as a fallback. The command exits with status 2 if neither kind of
    backend is available.
    """
    source = require_supported(source)
    target = require_supported(target)
    if source == target:
        raise click.BadParameter("--from and --to must differ")
    if cutoff is not None and level is not None:
        raise click.BadParameter("--cutoff and --level are mutually exclusive")
    if level is not None:
        cutoff = cefr_cutoff(source, level)
        click.echo(f"CEFR {level.upper()} → Zipf cutoff {cutoff:.2f} for {source!r}")
    elif cutoff is None:
        cutoff = 3.0

    output = output or input_epub.with_suffix(".annotated.epub")

    backends: list[Dictionary] = [
        DictCCDictionary.from_file(path, source, target) for path in dictcc_paths
    ]

    wikt = WiktionaryDictionary(source)
    if wikt.is_available:
        backends.append(wikt)

    if not backends:
        click.echo(
            "No dictionary backend available. Either provide --dictcc FILE or run "
            f"'build-wiktionary-index --source {source} path/to/kaikki.jsonl'.",
            err=True,
        )
        sys.exit(2)

    dictionary = backends[0] if len(backends) == 1 else CompositeDictionary(backends)

    annotator = Annotator(
        dictionary,
        AnnotationConfig(
            source_lang=source,
            target_lang=target,
            cutoff=cutoff,
            fmt=AnnotationFormat(fmt),
        ),
    )
    stats = annotate_epub(input_epub, output, annotator)
    click.echo(
        f"Annotated {stats.text_nodes_processed} text nodes across "
        f"{stats.documents_processed} documents → {output}"
    )


if __name__ == "__main__":
    main()
