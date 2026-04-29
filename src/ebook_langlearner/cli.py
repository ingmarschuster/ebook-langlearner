"""Command-line interface for ebook-langlearner.

Subcommands:

* ``languages``               — list supported language codes.
* ``build-wiktionary-index``  — convert a Kaikki JSONL dump into a SQLite index.
* ``build-dictcc-index``      — ingest one or more dict.cc TSV exports into a
  per-language-pair SQLite cache.
* ``list-dictcc-indexes``     — show the language pairs that have a cached
  dict.cc index.
* ``fetch-wiktionary``        — download and index a Kaikki Wiktionary dump.
* ``annotate``                — annotate an EPUB using configured dictionaries.
* ``set-level``               — switch the visible CEFR level of an annotated
  EPUB without re-annotating it.
* ``strip-annotations``       — remove every annotation, recovering the
  original prose.

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
    DictCCIndex,
    WiktionaryDictionary,
)
from .dictionaries.dictcc import (
    build_dictcc_index,
    dictcc_index_path_for,
    ensure_dictcc_index,
    list_indexed_dictcc_pairs,
)
from .dictionaries.download import (
    KAIKKI_LANGUAGE_NAMES,
    KaikkiDownloadError,
    ensure_wiktionary_index,
)
from .dictionaries.wiktionary import build_index, index_path_for
from .epub_pipeline import (
    MissingStylesheetError,
    annotate_epub,
    set_visible_level,
    strip_annotations,
)
from .languages import CORE_LANGUAGES, require_supported
from .render import DEFAULT_ANNOTATION_GREY_PCT, DEFAULT_RUBY_FONT_PCT, AnnotationFormat

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
        "Zipf-frequency cutoff: words strictly below this get tagged. "
        "Defaults to the A1 cutoff for the source language, so every word "
        "an A1 learner would want is annotated; pass a lower value to "
        "limit annotations to rarer words."
    ),
)
@click.option(
    "--level",
    type=click.Choice(CEFR_LEVELS, case_sensitive=False),
    default="B2",
    show_default=True,
    help=(
        "CEFR level whose annotations are visible by default. Words at all "
        "levels are still tagged; this only chooses which the reader sees. "
        "Switch later with 'set-level' without re-annotating."
    ),
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
    "--no-download",
    "no_download",
    is_flag=True,
    default=False,
    help=(
        "Do not auto-download a Wiktionary dump if no dict.cc is provided. "
        "Without this flag, the source-language Kaikki JSONL is fetched and "
        "indexed on first use (large, one-time download)."
    ),
)
@click.option(
    "--ruby-font-pct",
    type=click.FloatRange(min=50.0, max=120.0),
    default=DEFAULT_RUBY_FONT_PCT,
    show_default=True,
    help=(
        "Ruby translation font-size as a percentage of the base word's "
        "font-size. Lower = smaller annotation."
    ),
)
@click.option(
    "--annotation-grey-pct",
    type=click.FloatRange(min=50.0, max=100.0),
    default=DEFAULT_ANNOTATION_GREY_PCT,
    show_default=True,
    help=(
        "Annotation text darkness as a percentage (100 = black, 50 = mid-grey). "
        "Lower values make translations lighter so they feel less intrusive."
    ),
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
    level: str,
    fmt: str,
    dictcc_paths: tuple[Path, ...],
    *,
    no_download: bool,
    ruby_font_pct: float,
    annotation_grey_pct: float,
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
    a1_cutoff = cefr_cutoff(source, "A1")
    if cutoff is None:
        cutoff = a1_cutoff
    active_level = level.upper()
    click.echo(
        f"Tagging words below Zipf {cutoff:.2f} for {source!r}; "
        f"visible level: {active_level} (A1 cutoff {a1_cutoff:.2f})"
    )

    output = output or input_epub.with_suffix(".annotated.epub")

    backends: list[Dictionary] = []
    if dictcc_paths:
        # Build (or refresh) the cached SQLite for this pair the first time
        # the user passes a TSV; subsequent runs reuse the cache.
        ensure_dictcc_index(list(dictcc_paths), source, target)
    cached_dictcc = DictCCIndex(source, target)
    if cached_dictcc.is_available:
        backends.append(cached_dictcc)

    if not backends and not no_download and source in KAIKKI_LANGUAGE_NAMES:
        try:
            ensure_wiktionary_index(source, progress=_cli_download_progress)
        except KaikkiDownloadError as exc:
            click.echo(f"Wiktionary auto-download failed: {exc}", err=True)
            sys.exit(2)

    wikt = WiktionaryDictionary(source)
    if wikt.is_available:
        backends.append(wikt)

    if not backends:
        click.echo(
            "No dictionary backend available. Either provide --dictcc FILE (it will be "
            "indexed once and reused), drop --no-download to fetch the Kaikki Wiktionary "
            f"index automatically, or run 'build-wiktionary-index --source {source} "
            "path/to/kaikki.jsonl'.",
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
            ruby_font_pct=ruby_font_pct,
            annotation_grey_pct=annotation_grey_pct,
            active_level=active_level,
        ),
    )
    stats = annotate_epub(input_epub, output, annotator)
    click.echo(
        f"Annotated {stats.text_nodes_processed} text nodes across "
        f"{stats.documents_processed} documents → {output}"
    )


@main.command("build-dictcc-index")
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
    help="Target language code (e.g. en). Run 'languages' to list supported codes.",
)
@click.argument("tsv", nargs=-1, required=True, type=click.Path(exists=True, path_type=Path))
def cmd_build_dictcc_index(source: str, target: str, tsv: tuple[Path, ...]) -> None:
    """Ingest one or more dict.cc TSV exports into the per-pair cache.

    The cache lives under the user's data directory and is consulted
    automatically by ``annotate`` whenever the requested language pair has
    a built index. Pass several TSV paths to merge them into a single
    index; this is the right thing if you have, for example, both the
    main dict.cc download and a hand-curated supplement.
    """
    source = require_supported(source)
    target = require_supported(target)
    if source == target:
        raise click.BadParameter("--from and --to must differ")
    out = build_dictcc_index(list(tsv), source, target)
    click.echo(f"Built dict.cc index ({source} → {target}): {out}")


@main.command("list-dictcc-indexes")
def cmd_list_dictcc_indexes() -> None:
    """Print the language pairs that have a built dict.cc cache."""
    pairs = list_indexed_dictcc_pairs()
    if not pairs:
        click.echo("No dict.cc indexes have been built yet.")
        return
    for src, tgt in pairs:
        click.echo(f"{src} → {tgt}\t{dictcc_index_path_for(src, tgt)}")


@main.command("set-level")
@click.argument("input_epub", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--level",
    type=click.Choice(CEFR_LEVELS, case_sensitive=False),
    required=True,
    help="CEFR level to make visible (case-insensitive).",
)
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output EPUB path. Defaults to <input>.<level>.epub.",
)
def cmd_set_level(input_epub: Path, level: str, output: Path | None) -> None:
    """Switch the visible CEFR level of an annotated EPUB.

    The book's annotations are tagged at every level when produced; this
    command rewrites only the active-level CSS block so a different level
    becomes visible. Switching is fast and lossless — no re-annotation, no
    dictionary lookups.
    """
    lower = level.lower()
    output = output or input_epub.with_suffix(f".{lower}.epub")
    try:
        set_visible_level(input_epub, output, level)
    except MissingStylesheetError as exc:
        click.echo(f"Cannot switch level: {exc}", err=True)
        click.echo(
            "Re-annotate the book with this version of ebook-langlearner first.",
            err=True,
        )
        sys.exit(2)
    click.echo(f"Visible level switched to {level.upper()} → {output}")


@main.command("strip-annotations")
@click.argument("input_epub", type=click.Path(exists=True, path_type=Path))
@click.option(
    "--output",
    "-o",
    type=click.Path(path_type=Path),
    help="Output EPUB path. Defaults to <input>.stripped.epub.",
)
def cmd_strip_annotations(input_epub: Path, output: Path | None) -> None:
    """Remove every annotation from an EPUB, recovering the original prose.

    Drops the bundled annotation stylesheet and unwraps every ``ell-annot``
    element so the resulting EPUB reads like the unannotated source.
    """
    output = output or input_epub.with_suffix(".stripped.epub")
    stats = strip_annotations(input_epub, output)
    click.echo(
        f"Stripped {stats.annotations_removed} annotations across "
        f"{stats.documents_processed} documents → {output}"
    )


@main.command("fetch-wiktionary")
@click.option(
    "--source",
    "-s",
    required=True,
    help="Source language code (e.g. fr). Run 'languages' to list supported codes.",
)
@click.option(
    "--force",
    is_flag=True,
    default=False,
    help="Re-download and rebuild even if an index already exists.",
)
def cmd_fetch_wiktionary(source: str, *, force: bool) -> None:
    """Download and index the Kaikki Wiktionary dump for ``source``.

    Once cached, subsequent ``annotate`` calls without ``--dictcc`` will use
    this index automatically. Run this ahead of time on a fast connection if
    you don't want the first ``annotate`` invocation to also be a
    multi-hundred-megabyte download.
    """
    source = require_supported(source)
    if force:
        index = index_path_for(source)
        if index.exists():
            index.unlink()
    try:
        path = ensure_wiktionary_index(source, progress=_cli_download_progress)
    except KaikkiDownloadError as exc:
        click.echo(f"Download failed: {exc}", err=True)
        sys.exit(2)
    click.echo(f"\nWiktionary index ready: {path}")


_PCT_COMPLETE = 100
_LAST_PCT: dict[str, int] = {"value": -1}
"""Per-process throttle for download-progress lines so we don't spam stderr."""


def _cli_download_progress(stage: str, current: int, total: int | None) -> None:
    """Stream Kaikki download/indexing progress to stderr.

    Prints the download percentage at integer-percent granularity (so a
    multi-hundred-megabyte fetch produces ~100 status lines, not millions).
    Falls back to a byte count when ``Content-Length`` is missing.
    """
    if stage == "indexing":
        click.echo("Indexing Kaikki dump into SQLite…", err=True)
        _LAST_PCT["value"] = -1
        return
    if total:
        pct = int(current * _PCT_COMPLETE / total)
        if pct == _LAST_PCT["value"]:
            return
        _LAST_PCT["value"] = pct
        click.echo(
            f"\rDownloading Kaikki dump: {pct:3d}%  "
            f"({current / 1_048_576:.1f} / {total / 1_048_576:.1f} MiB)",
            err=True,
            nl=False,
        )
        if pct == _PCT_COMPLETE:
            click.echo("", err=True)
    else:
        click.echo(
            f"\rDownloading Kaikki dump: {current / 1_048_576:.1f} MiB",
            err=True,
            nl=False,
        )


if __name__ == "__main__":
    main()
