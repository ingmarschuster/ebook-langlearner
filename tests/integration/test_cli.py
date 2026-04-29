"""End-to-end CLI tests using Click's :class:`CliRunner`.

The CLI is the primary user surface, so smoke-test that user-visible options
(``--ruby-font-pct`` here) round-trip into the produced EPUB rather than
silently being dropped on the floor.
"""

from __future__ import annotations

import http.server
import json
import threading
import zipfile
from typing import TYPE_CHECKING

import pytest
from click.testing import CliRunner

from ebook_langlearner.cli import main
from ebook_langlearner.epub_pipeline import STYLESHEET_FILENAME

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path


@pytest.fixture
def isolated_cli_cache(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the shared cache to the test's tmp_path and return that path.

    The CLI caches dict.cc and Wiktionary indexes under the user cache dir;
    tests that build or assert on cached files must use this to avoid
    leaking artifacts into the real user cache.
    """
    cache = tmp_path / "user-cache"
    cache.mkdir()
    monkeypatch.setattr("ebook_langlearner.dictionaries.wiktionary.cache_dir", lambda: cache)
    return cache


@pytest.fixture(autouse=True)
def _isolate_user_cache(isolated_cli_cache: Path) -> None:
    """Apply :func:`isolated_cli_cache` to every test in this module."""
    del isolated_cli_cache


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


_AUTO_DOWNLOAD_FIXTURE = (
    json.dumps({"word": "aubépine", "translations": [{"code": "en", "word": "hawthorn"}]})
    + "\n"
    + json.dumps({"word": "crépuscule", "translations": [{"code": "en", "word": "twilight"}]})
    + "\n"
).encode("utf-8")


class _CliFixtureHandler(http.server.BaseHTTPRequestHandler):
    expected_path = "/dictionary/French/kaikki.org-dictionary-French.jsonl"

    def do_GET(self) -> None:
        if self.path != self.expected_path:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Length", str(len(_AUTO_DOWNLOAD_FIXTURE)))
        self.end_headers()
        self.wfile.write(_AUTO_DOWNLOAD_FIXTURE)

    def log_message(self, *_args: object, **_kwargs: object) -> None:
        return


@pytest.fixture
def cli_fixture_server() -> Generator[str, None, None]:
    server = http.server.HTTPServer(("127.0.0.1", 0), _CliFixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/dictionary"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_annotate_auto_downloads_when_no_dictcc(
    minimal_epub: Path,
    cli_fixture_server: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """Without --dictcc, the CLI must fetch + index the Wiktionary dump."""
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr("ebook_langlearner.dictionaries.wiktionary.cache_dir", lambda: cache)
    monkeypatch.setattr(
        "ebook_langlearner.dictionaries.download.KAIKKI_BASE_URL",
        cli_fixture_server,
    )
    # The CLI looks up KAIKKI_BASE_URL via the module attribute at call time,
    # so monkeypatching the module-level binding is sufficient.

    output = tmp_path / "out.epub"
    result = CliRunner().invoke(
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
            "--output",
            str(output),
        ],
    )
    assert result.exit_code == 0, result.output
    # Fixture got fetched and indexed under the patched cache dir.
    assert (cache / "kaikki-fr.jsonl").exists()
    assert (cache / "wiktionary-fr.sqlite").exists()
    assert output.exists()


def test_build_dictcc_index_caches_and_annotate_reuses_it(
    minimal_epub: Path,
    tiny_dictcc_file: Path,
    tmp_path: Path,
    isolated_cli_cache: Path,
):
    """``build-dictcc-index`` writes the cache; later ``annotate`` reuses it offline."""
    runner = CliRunner()
    built = runner.invoke(
        main,
        [
            "build-dictcc-index",
            "--from",
            "fr",
            "--to",
            "en",
            str(tiny_dictcc_file),
        ],
    )
    assert built.exit_code == 0, built.output
    assert (isolated_cli_cache / "dictcc-fr-en.sqlite").exists()

    listed = runner.invoke(main, ["list-dictcc-indexes"])
    assert listed.exit_code == 0
    assert "fr → en" in listed.output

    # Second call: annotate without --dictcc and --no-download must succeed
    # purely from the cached SQLite index.
    output = tmp_path / "out.epub"
    annot = runner.invoke(
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
            "--no-download",
            "--output",
            str(output),
        ],
    )
    assert annot.exit_code == 0, annot.output
    assert output.exists()


def test_annotate_no_download_flag_blocks_auto_fetch(
    minimal_epub: Path,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """``--no-download`` must keep the CLI offline even when no backend is configured."""
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr("ebook_langlearner.dictionaries.wiktionary.cache_dir", lambda: cache)

    result = CliRunner().invoke(
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
            "--no-download",
            "--output",
            str(tmp_path / "out.epub"),
        ],
    )
    assert result.exit_code == 2
    assert "no dictionary backend" in result.output.lower()
    # No fetch happened.
    assert not (cache / "kaikki-fr.jsonl").exists()
