"""Auto-download Kaikki Wiktionary JSONL dumps.

Kaikki.org publishes one big postprocessed JSONL extraction per source
Wiktionary edition. The files are large (tens to hundreds of MB) but each
is a one-time fetch — once downloaded and indexed into SQLite via
:func:`dictionaries.wiktionary.build_index`, lookups are local and fast.

The download uses :mod:`urllib.request` from the standard library so the
Calibre plugin doesn't need to vendor an HTTP client. ``$HTTP_PROXY`` /
``$HTTPS_PROXY`` env vars are honored automatically by ``urllib``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from . import wiktionary as _wiktionary

if TYPE_CHECKING:
    from collections.abc import Callable
    from pathlib import Path


# ISO 639-1 → English language name as Kaikki spells it in URLs. This is the
# slug used in the postprocessed JSONL location, and unfortunately differs
# from the ISO codes (Kaikki uses English exonyms, not BCP-47 tags).
KAIKKI_LANGUAGE_NAMES: dict[str, str] = {
    "de": "German",
    "en": "English",
    "es": "Spanish",
    "fr": "French",
    "it": "Italian",
    "nl": "Dutch",
    "pl": "Polish",
    "pt": "Portuguese",
    "sv": "Swedish",
}

KAIKKI_BASE_URL = "https://kaikki.org/dictionary"
"""Origin for Kaikki postprocessed extractions. Override for testing."""

DOWNLOAD_CHUNK_BYTES = 1 << 20
"""1 MiB chunks: large enough to keep syscall overhead negligible, small
enough that progress callbacks fire often on multi-hundred-MB files."""

USER_AGENT = "ebook-langlearner (+https://github.com/ingmarschuster/ebook-langlearner)"
"""Kaikki returns 403 to clients that don't send a User-Agent. Identifying
ourselves is also good citizenship for a public free-data host."""


ProgressFn = "Callable[[int, int | None], None]"
"""Progress callback signature: ``(downloaded_bytes, total_bytes_or_None)``.

``total_bytes`` is ``None`` when the server doesn't send ``Content-Length``.
"""


class KaikkiDownloadError(RuntimeError):
    """Raised when a Kaikki dump cannot be fetched."""


def kaikki_url(source_lang: str, *, base_url: str | None = None) -> str:
    """Return the Kaikki postprocessed-JSONL URL for ``source_lang``.

    Args:
        source_lang: ISO 639-1 code; must be a key of
            :data:`KAIKKI_LANGUAGE_NAMES`.
        base_url: Override for the host. ``None`` (default) reads
            :data:`KAIKKI_BASE_URL` at call time so tests can monkeypatch
            the module attribute.

    Raises:
        KeyError: If ``source_lang`` is not in :data:`KAIKKI_LANGUAGE_NAMES`.
    """
    name = KAIKKI_LANGUAGE_NAMES[source_lang]
    base = KAIKKI_BASE_URL if base_url is None else base_url
    return f"{base}/{name}/kaikki.org-dictionary-{name}.jsonl"


def download_kaikki_dump(
    source_lang: str,
    dest: Path,
    *,
    progress: Callable[[int, int | None], None] | None = None,
    base_url: str | None = None,
) -> Path:
    """Stream the Kaikki postprocessed JSONL dump for ``source_lang`` to ``dest``.

    The download is written to ``dest.with_suffix(dest.suffix + ".part")``
    first and renamed on success so a half-written file from an interrupted
    run is never picked up as a complete index source.

    Args:
        source_lang: ISO 639-1 code.
        dest: Final on-disk path for the JSONL.
        progress: Optional callback invoked roughly every
            :data:`DOWNLOAD_CHUNK_BYTES` with
            ``(downloaded_bytes, total_bytes_or_None)``.
        base_url: Override for the Kaikki host (testing).

    Raises:
        KaikkiDownloadError: If the HTTP request fails.

    Returns:
        ``dest`` on success.
    """
    url = kaikki_url(source_lang, base_url=base_url)
    if not url.startswith(("http://", "https://")):
        msg = f"refusing to fetch non-http(s) URL: {url!r}"
        raise KaikkiDownloadError(msg)
    request = Request(url, headers={"User-Agent": USER_AGENT})
    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        with urlopen(request) as response:
            length_header = response.headers.get("Content-Length")
            total = int(length_header) if length_header else None
            downloaded = 0
            with tmp.open("wb") as fh:
                while True:
                    chunk = response.read(DOWNLOAD_CHUNK_BYTES)
                    if not chunk:
                        break
                    fh.write(chunk)
                    downloaded += len(chunk)
                    if progress is not None:
                        progress(downloaded, total)
    except (HTTPError, URLError) as exc:
        if tmp.exists():
            tmp.unlink()
        msg = f"failed to download Kaikki dump for {source_lang!r} from {url}: {exc}"
        raise KaikkiDownloadError(msg) from exc
    tmp.replace(dest)
    return dest


def ensure_wiktionary_index(
    source_lang: str,
    *,
    progress: Callable[[str, int, int | None], None] | None = None,
    base_url: str | None = None,
) -> Path:
    """Return a usable Wiktionary SQLite index, downloading + building if missing.

    No-op if an index for ``source_lang`` already exists in the user's cache.

    Args:
        source_lang: ISO 639-1 code.
        progress: Optional callback invoked as
            ``(stage, current_bytes, total_bytes_or_None)`` where ``stage`` is
            ``"downloading"`` or ``"indexing"``. ``current_bytes`` is 0 when
            indexing (size is not meaningful there).
        base_url: Override for the Kaikki host (testing).

    Returns:
        Path to the SQLite index file.
    """
    index = _wiktionary.index_path_for(source_lang)
    if index.exists():
        return index

    jsonl = _wiktionary.cache_dir() / f"kaikki-{source_lang}.jsonl"
    if not jsonl.exists():

        def _on_chunk(current: int, total: int | None) -> None:
            if progress is not None:
                progress("downloading", current, total)

        download_kaikki_dump(source_lang, jsonl, progress=_on_chunk, base_url=base_url)

    if progress is not None:
        progress("indexing", 0, None)
    _wiktionary.build_index(source_lang, jsonl, index_path=index)
    return index
