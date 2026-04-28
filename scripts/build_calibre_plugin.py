"""Assemble the Calibre plugin zip.

Steps:

1. Mirror ``src/ebook_langlearner`` into ``calibre-plugin/ell/`` so the
   pipeline source ships unmodified inside the plugin namespace.
2. Vendor ``ebooklib`` (pure Python, ~170 KB) into
   ``calibre-plugin/vendor/`` so the plugin does not rely on Calibre's
   embedded Python having third-party packages installed.
3. Vendor ``simplemma`` and ``wordfreq``, pruning each one's per-language
   data files to only the codes in
   :data:`ebook_langlearner.languages.CORE_LANGUAGES` to keep the zip small.
4. Render the source SVG icon to ``calibre-plugin/images/icon.png`` so the
   zip ships a 48 px PNG that Calibre can use for the toolbar action.
5. Zip the plugin directory flat into ``dist/ebook-langlearner-<version>.zip``.

Missing build/runtime dependencies are pip-installed into ``build/_deps/``
on demand, so a fresh checkout produces a usable zip without the developer
having to ``uv sync`` the optional build extras first.

Run via ``uv run python scripts/build_calibre_plugin.py``.
"""

from __future__ import annotations

import importlib
import importlib.util
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SRC = REPO / "src" / "ebook_langlearner"
PLUGIN = REPO / "calibre-plugin"
DIST = REPO / "dist"
BUILD_DEPS = REPO / "build" / "_deps"
VERSION = "0.1.0"

CORE_LANGS: frozenset[str] = frozenset({"de", "en", "es", "fr", "it", "nl", "pl", "pt", "sv"})


def _ensure_installed(pkg_name: str, *, pip_name: str | None = None) -> Path:
    """Return the on-disk source directory of ``pkg_name``, installing if missing.

    Looks in the current environment first; if ``pkg_name`` is not importable
    there, pip-installs ``pip_name`` (defaults to ``pkg_name``) into
    ``build/_deps/`` and adds that directory to ``sys.path`` so the spec
    lookup succeeds on the second attempt. Keeps the build self-sufficient
    against partial dev environments.
    """
    spec = importlib.util.find_spec(pkg_name)
    if spec is None or not spec.submodule_search_locations:
        target = BUILD_DEPS
        target.mkdir(parents=True, exist_ok=True)
        if str(target) not in sys.path:
            sys.path.insert(0, str(target))
        print(f"  installing {pkg_name} into {target.relative_to(REPO)}")
        subprocess.run(
            _pip_install_cmd(target, pip_name or pkg_name),
            check=True,
        )
        importlib.invalidate_caches()
        spec = importlib.util.find_spec(pkg_name)
    if spec is None or not spec.submodule_search_locations:
        msg = f"{pkg_name} could not be installed or located"
        raise SystemExit(msg)
    return Path(spec.submodule_search_locations[0])


def _pip_install_cmd(target: Path, requirement: str) -> list[str]:
    """Build the install command, preferring ``uv pip`` when available.

    ``uv``-managed virtualenvs ship without ``pip``, so ``python -m pip`` fails
    inside them. When the ``uv`` binary is on PATH we use ``uv pip install
    --target`` instead; otherwise we fall back to ``python -m pip`` for
    classic CPython environments.
    """
    uv = shutil.which("uv")
    if uv is not None:
        return [uv, "pip", "install", "--quiet", "--target", str(target), requirement]
    return [
        sys.executable,
        "-m",
        "pip",
        "install",
        "--quiet",
        "--target",
        str(target),
        requirement,
    ]


def _copy_tree(src: Path, dst: Path) -> None:
    """Replace ``dst`` with a fresh copy of ``src``, skipping ``__pycache__``."""
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(src, dst, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def _prune_lang_data(directory: Path, suffix: str) -> int:
    """Remove ``<lang>{suffix}`` files in ``directory`` for non-core languages.

    Returns the number of files deleted, for the build log.
    """
    if not directory.is_dir():
        return 0
    removed = 0
    for entry in directory.iterdir():
        if not entry.is_file() or not entry.name.endswith(suffix):
            continue
        lang_part = entry.name[: -len(suffix)]
        lang = lang_part.split("_")[-1]
        if lang not in CORE_LANGS:
            entry.unlink()
            removed += 1
    return removed


def build_ell() -> None:
    """Mirror ``src/ebook_langlearner`` into ``calibre-plugin/ell/``.

    Re-creates the ``.gitkeep`` sentinel afterwards so the placeholder that
    keeps the (otherwise gitignored) directory tracked survives every build.
    """
    dst = PLUGIN / "ell"
    _copy_tree(SRC, dst)
    (dst / ".gitkeep").touch()


def build_ebooklib() -> None:
    """Vendor the ``ebooklib`` source tree into ``calibre-plugin/vendor/``."""
    _copy_tree(_ensure_installed("ebooklib", pip_name="EbookLib"), PLUGIN / "vendor" / "ebooklib")


def build_simplemma() -> None:
    """Vendor ``simplemma`` and prune per-language model files outside the core set."""
    dst = PLUGIN / "vendor" / "simplemma"
    _copy_tree(_ensure_installed("simplemma"), dst)
    n = _prune_lang_data(dst / "strategies" / "dictionaries" / "data", ".plzma")
    print(f"  simplemma: pruned {n} non-core language data files")


def build_wordfreq() -> None:
    """Vendor ``wordfreq`` and prune per-language msgpack data outside the core set."""
    dst = PLUGIN / "vendor" / "wordfreq"
    _copy_tree(_ensure_installed("wordfreq"), dst)
    data = dst / "data"
    n = _prune_lang_data(data, ".msgpack.gz")
    # Keep the Chinese mapping table (named without a language suffix) and any
    # remaining language-agnostic resources; only language-specific msgpack
    # files were pruned above.
    print(f"  wordfreq: pruned {n} non-core msgpack files")


def build_icon() -> None:
    """Render ``calibre-plugin/icon.svg`` to a 48 px ``images/icon.png``.

    Pip-installs ``cairosvg`` into ``build/_deps`` on demand if it is not
    already importable, so a clean checkout produces a real raster icon
    without manual setup. ``cairosvg`` needs the native ``libcairo`` library
    at runtime; if it is missing (common on a fresh macOS install) we emit a
    one-line hint with the platform's install command and skip the icon.
    The plugin still works without it — Calibre falls back to a generic
    puzzle-piece glyph.
    """
    svg = PLUGIN / "icon.svg"
    out_dir = PLUGIN / "images"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / "icon.png"
    if not svg.is_file():
        print("  icon: icon.svg missing, skipping")
        return
    _ensure_installed("cairosvg")
    try:
        cairosvg = importlib.import_module("cairosvg")
    except OSError as exc:
        print(f"  icon: skipped (libcairo unavailable: {exc.__class__.__name__})")
        print(f"        install it with: {_libcairo_install_hint()}")
        return
    cairosvg.svg2png(url=str(svg), write_to=str(out), output_width=48, output_height=48)
    print(f"  icon: rendered {out.relative_to(REPO)}")


def _libcairo_install_hint() -> str:
    """Return the platform-appropriate command to install native libcairo."""
    if sys.platform == "darwin":
        return "brew install cairo"
    if sys.platform.startswith("linux"):
        return "apt install libcairo2  (or your distro's equivalent)"
    return "see https://www.cairographics.org/download/"


def write_zip() -> Path:
    """Zip the plugin directory flat into ``dist/ebook-langlearner-<version>.zip``."""
    DIST.mkdir(exist_ok=True)
    out = DIST / f"ebook-langlearner-{VERSION}.zip"
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(PLUGIN.rglob("*")):
            if not path.is_file():
                continue
            if "__pycache__" in path.parts or path.suffix == ".pyc":
                continue
            zf.write(path, path.relative_to(PLUGIN))
    return out


def main() -> int:
    """Run the full build and report the final zip path and size."""
    print("Building Calibre plugin payload...")
    build_ell()
    build_ebooklib()
    build_simplemma()
    build_wordfreq()
    build_icon()
    out = write_zip()
    size_mb = out.stat().st_size / (1024 * 1024)
    print(f"\nWrote {out.relative_to(REPO)} ({size_mb:.1f} MB)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
