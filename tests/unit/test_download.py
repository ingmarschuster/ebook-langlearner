"""Tests for the Kaikki Wiktionary auto-downloader.

We never hit kaikki.org in tests — instead we spin up a local
:class:`http.server.HTTPServer` on an ephemeral port and serve a tiny
fixture JSONL. That exercises the real ``urllib.request`` code path
including streaming, ``Content-Length`` handling, and ``.part``-file
atomic-rename without depending on the network.
"""

from __future__ import annotations

import http.server
import json
import threading
from typing import TYPE_CHECKING

import pytest

from ebook_langlearner.dictionaries.download import (
    KAIKKI_LANGUAGE_NAMES,
    KaikkiDownloadError,
    download_kaikki_dump,
    ensure_wiktionary_index,
    kaikki_url,
)
from ebook_langlearner.dictionaries.wiktionary import index_path_for
from ebook_langlearner.languages import CORE_LANGUAGES

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path


def _entry(word: str, translation: str, target: str = "en") -> dict:
    return {
        "word": word,
        "translations": [{"code": target, "word": translation}],
    }


JSONL_FIXTURE = (
    json.dumps(_entry("aubépine", "hawthorn"))
    + "\n"
    + json.dumps(_entry("crépuscule", "twilight"))
    + "\n"
).encode("utf-8")


class _FixtureHandler(http.server.BaseHTTPRequestHandler):
    """Serves the JSONL fixture at the Kaikki URL pattern; 404s otherwise."""

    expected_path = "/dictionary/French/kaikki.org-dictionary-French.jsonl"

    def do_GET(self) -> None:
        if self.path != self.expected_path:
            self.send_response(404)
            self.end_headers()
            return
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.send_header("Content-Length", str(len(JSONL_FIXTURE)))
        self.end_headers()
        self.wfile.write(JSONL_FIXTURE)

    def log_message(self, *_args: object, **_kwargs: object) -> None:
        # Silence the default access-log spam during tests.
        return


@pytest.fixture
def fixture_server() -> Generator[str, None, None]:
    """Spin up a localhost HTTP server serving the JSONL fixture; yield its base URL."""
    server = http.server.HTTPServer(("127.0.0.1", 0), _FixtureHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        host, port = server.server_address
        yield f"http://{host}:{port}/dictionary"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def test_kaikki_url_uses_english_language_name():
    assert kaikki_url("fr") == (
        "https://kaikki.org/dictionary/French/kaikki.org-dictionary-French.jsonl"
    )
    assert kaikki_url("de").endswith("German/kaikki.org-dictionary-German.jsonl")


def test_kaikki_url_rejects_unknown_language():
    with pytest.raises(KeyError):
        kaikki_url("xx")


def test_kaikki_language_names_covers_core_set():
    # Every supported source language must have a Kaikki slug, otherwise the
    # auto-download path will KeyError at runtime for that language.
    assert set(KAIKKI_LANGUAGE_NAMES) == set(CORE_LANGUAGES)


def test_download_kaikki_dump_streams_to_disk(fixture_server: str, tmp_path: Path):
    dest = tmp_path / "fr.jsonl"
    progress_calls: list[tuple[int, int | None]] = []
    download_kaikki_dump(
        "fr",
        dest,
        progress=lambda c, t: progress_calls.append((c, t)),
        base_url=fixture_server,
    )
    assert dest.read_bytes() == JSONL_FIXTURE
    # At least one progress call must have fired and reported the total size.
    assert progress_calls, "progress callback should fire at least once"
    final_current, final_total = progress_calls[-1]
    assert final_current == len(JSONL_FIXTURE)
    assert final_total == len(JSONL_FIXTURE)


def test_download_kaikki_dump_uses_atomic_rename(fixture_server: str, tmp_path: Path):
    """A ``.part`` file must not survive a successful download."""
    dest = tmp_path / "fr.jsonl"
    download_kaikki_dump("fr", dest, base_url=fixture_server)
    assert dest.exists()
    assert not dest.with_suffix(dest.suffix + ".part").exists()


def test_download_raises_on_404(fixture_server: str, tmp_path: Path):
    """An unknown source language whose URL the fixture server doesn't serve."""
    # Point at a base URL that exists but with a slug the handler will 404.
    bad_base = fixture_server + "/missing"
    with pytest.raises(KaikkiDownloadError):
        download_kaikki_dump("fr", tmp_path / "fr.jsonl", base_url=bad_base)
    # Failed download must not leave a partial file behind.
    assert not (tmp_path / "fr.jsonl.part").exists()


def test_ensure_wiktionary_index_downloads_and_builds(
    fixture_server: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """End-to-end: no cache → download → build index → return existing path on second call."""
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr("ebook_langlearner.dictionaries.wiktionary.cache_dir", lambda: cache)

    progress_stages: list[str] = []

    def _progress(stage: str, current: int, total: int | None) -> None:
        del current, total
        if not progress_stages or progress_stages[-1] != stage:
            progress_stages.append(stage)

    index = ensure_wiktionary_index("fr", progress=_progress, base_url=fixture_server)
    assert index == index_path_for("fr") == cache / "wiktionary-fr.sqlite"
    assert index.exists()
    assert progress_stages == ["downloading", "indexing"]

    # The Kaikki JSONL must also be cached so subsequent rebuilds don't redownload.
    assert (cache / "kaikki-fr.jsonl").exists()

    # Second call: no work, no progress events.
    progress_stages.clear()
    again = ensure_wiktionary_index("fr", progress=_progress, base_url=fixture_server)
    assert again == index
    assert progress_stages == []


def test_ensure_wiktionary_index_reuses_existing_jsonl(
    fixture_server: str,
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
):
    """If the JSONL is already cached but the SQLite isn't, rebuild without redownloading."""
    cache = tmp_path / "cache"
    cache.mkdir()
    monkeypatch.setattr("ebook_langlearner.dictionaries.wiktionary.cache_dir", lambda: cache)
    (cache / "kaikki-fr.jsonl").write_bytes(JSONL_FIXTURE)

    progress_stages: list[str] = []

    def _progress(stage: str, current: int, total: int | None) -> None:
        del current, total
        progress_stages.append(stage)

    # Use a base URL that 404s — proves we never hit the network.
    ensure_wiktionary_index("fr", progress=_progress, base_url=fixture_server + "/missing")
    assert (cache / "wiktionary-fr.sqlite").exists()
    assert "downloading" not in progress_stages
    assert "indexing" in progress_stages
