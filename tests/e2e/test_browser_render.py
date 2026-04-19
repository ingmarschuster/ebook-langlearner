"""Browser-level end-to-end test: render an annotated EPUB with epub.js.

This test proves the annotations produced by the pipeline actually reach a
reader: it opens the annotated EPUB in a real headless Chromium via
Playwright, loads the book with the epub.js open-source renderer, and checks
that ruby annotations are present and populated in the rendered DOM.

The test is marked ``e2e`` and is skipped when Playwright's browsers are not
installed, so a clean checkout without ``playwright install`` still has a
green unit/integration run.
"""

from __future__ import annotations

import http.server
import shutil
import socketserver
import threading
from contextlib import contextmanager
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from ebook_langlearner.annotate import AnnotationConfig, Annotator
from ebook_langlearner.epub_pipeline import annotate_epub
from ebook_langlearner.render import AnnotationFormat

# Skip the whole module if Playwright's Python bindings aren't installed; this
# keeps the default test run green on machines that don't have the browser
# dependency (the ``dev`` group pulls it in for CI and local e2e runs).
playwright_sync = pytest.importorskip("playwright.sync_api")

if TYPE_CHECKING:
    from collections.abc import Iterator

    from ebook_langlearner.dictionaries.base import Dictionary


RENDERER_HTML = Path(__file__).resolve().parent / "renderer.html"
RENDER_TIMEOUT_MS = 30_000


@contextmanager
def _serve_directory(directory: Path) -> Iterator[int]:
    """Serve ``directory`` over HTTP on a free port for the duration of the block.

    epub.js fetches book chapters and resources with same-origin requests, so
    the EPUB and the renderer HTML must both be loaded from ``http://``, not
    ``file://`` (where XHR is blocked).
    """

    class _Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *_args: object, **_kwargs: object) -> None:
            pass

        def __init__(self, *args: object, **kwargs: object) -> None:
            super().__init__(*args, directory=str(directory), **kwargs)

    with socketserver.TCPServer(("127.0.0.1", 0), _Handler) as httpd:
        port = httpd.server_address[1]
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        try:
            yield port
        finally:
            httpd.shutdown()
            thread.join(timeout=5)


@pytest.fixture
def chromium_page():
    """Yield a fresh Playwright Chromium page, skipping if browsers aren't installed."""
    with playwright_sync.sync_playwright() as p:
        try:
            browser = p.chromium.launch()
        except playwright_sync.Error as exc:
            pytest.skip(f"Chromium not installed for Playwright: {exc}")
        context = browser.new_context()
        page = context.new_page()
        try:
            yield page
        finally:
            context.close()
            browser.close()


@pytest.mark.e2e
def test_annotated_epub_renders_ruby_in_browser(
    minimal_epub: Path,
    permissive_fr_dict: Dictionary,
    tmp_path: Path,
    chromium_page,
):
    """End-to-end: pipeline output is readable by epub.js and shows ruby annotations."""
    annotated = tmp_path / "annotated.epub"
    annotator = Annotator(
        permissive_fr_dict,
        AnnotationConfig(
            source_lang="fr",
            target_lang="en",
            cutoff=3.5,
            fmt=AnnotationFormat.RUBY,
        ),
    )
    stats = annotate_epub(minimal_epub, annotated, annotator)
    assert stats.text_nodes_processed > 0, "pipeline must have produced some annotations"

    serve_root = tmp_path / "site"
    serve_root.mkdir()
    shutil.copy(RENDERER_HTML, serve_root / "renderer.html")
    shutil.copy(annotated, serve_root / "book.epub")

    with _serve_directory(serve_root) as port:
        url = f"http://127.0.0.1:{port}/renderer.html?epub=book.epub"
        chromium_page.goto(url, wait_until="load")
        chromium_page.wait_for_function(
            "() => window.__renderer && window.__renderer.ready",
            timeout=RENDER_TIMEOUT_MS,
        )
        ruby_count = chromium_page.evaluate("() => window.__renderer.rubyCount")
        first = chromium_page.evaluate("() => window.__renderer.firstRuby")

    assert ruby_count > 0, "rendered chapter must contain at least one ruby annotation"
    assert first is not None
    assert first["base"].strip(), "ruby base text must be non-empty"
    assert first["rt"].strip() == "TR", "rt translation should be the permissive-dict token"
