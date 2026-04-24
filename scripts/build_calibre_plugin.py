"""Assemble the Calibre plugin zip.

This script is a TODO skeleton; it documents the intended build steps but
does not yet execute them end-to-end. Enough code is present to create the
zip layout from the static parts (``calibre-plugin/*.py``, ``.txt`` marker,
READMEs) so the plugin boundary can be inspected.

Intended full flow:

1. Copy ``src/ebook_langlearner`` → ``calibre-plugin/ell/`` (fresh snapshot
   each build so the plugin picks up the latest pipeline code).
2. Copy the installed ``ebooklib`` package into ``calibre-plugin/vendor/``.
3. Copy the installed ``simplemma`` package into ``calibre-plugin/vendor/``,
   pruning per-language data for codes outside
   :data:`ebook_langlearner.languages.CORE_LANGUAGES`.
4. Precompute a surface-form Zipf table (parallel to the existing
   lemma-freq tables) so the plugin does not need to import ``wordfreq``
   at runtime. Drop it under ``calibre-plugin/ell/data/``.
5. Zip the ``calibre-plugin/`` directory flat into
   ``dist/ebook-langlearner-<version>.zip``.

Run via ``uv run python scripts/build_calibre_plugin.py``.
"""

from __future__ import annotations

import sys
import zipfile
from pathlib import Path

PLUGIN_DIR = Path(__file__).resolve().parent.parent / "calibre-plugin"
DIST_DIR = Path(__file__).resolve().parent.parent / "dist"
VERSION = "0.1.0"


def main() -> int:
    """Produce a zip from the static plugin layout (vendoring TODO)."""
    DIST_DIR.mkdir(exist_ok=True)
    out = DIST_DIR / f"ebook-langlearner-{VERSION}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(PLUGIN_DIR.rglob("*")):
            if path.is_file():
                zf.write(path, path.relative_to(PLUGIN_DIR))
    print(f"Wrote skeleton zip: {out.relative_to(Path.cwd())}")
    print("NOTE: vendored deps and precomputed surface-freq table are TODO.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
