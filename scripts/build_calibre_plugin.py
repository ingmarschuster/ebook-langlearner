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

import argparse
import ctypes.util
import importlib
import importlib.util
import os
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
VERSION = "0.1.2"

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
    """Vendor ``src/ebook_langlearner`` as ``vendor/ebook_langlearner``.

    The pipeline uses absolute imports (``from ebook_langlearner.X import
    Y``) per the project's TID252 ruff rule. To make those imports
    resolvable from inside the plugin, the source has to be reachable at
    its real package name on ``sys.path`` — which means vendoring it
    alongside the third-party packages instead of nesting it under the
    plugin's ``calibre_plugins.ell`` namespace.
    """
    _copy_tree(SRC, PLUGIN / "vendor" / "ebook_langlearner")


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


def build_wordfreq_deps() -> None:
    """Vendor runtime deps that Calibre's bundled Python does not ship.

    Includes wordfreq's transitive deps (``langcodes``, ``msgpack``, ``ftfy``,
    ``regex``, ``wcwidth``, ``locate``) plus ``platformdirs`` (used by
    ``wiktionary.py``) and ``bs4`` / ``beautifulsoup4`` (used by
    ``epub_pipeline.py``). Calibre provides ``lxml`` and ``soupsieve``, so
    those are intentionally omitted. C extensions (e.g. ``regex``'s
    ``_regex.*.so``) are copied from the build machine and must match the
    Python ABI Calibre embeds.
    """
    for pkg, pip_name in (
        ("langcodes", None),
        ("msgpack", None),
        ("ftfy", None),
        ("regex", None),
        ("wcwidth", None),
        ("locate", None),
        ("platformdirs", None),
        ("bs4", "beautifulsoup4"),
    ):
        _copy_tree(_ensure_installed(pkg, pip_name=pip_name), PLUGIN / "vendor" / pkg)


_LIBCAIRO_FALLBACK_DIRS = (
    "/opt/homebrew/lib",
    "/usr/local/lib",
    "/usr/lib/x86_64-linux-gnu",
    "/usr/lib/aarch64-linux-gnu",
    "/usr/lib64",
)
_LIBCAIRO_LEAFNAMES = ("libcairo.2.dylib", "libcairo.so.2")


def _libcairo_candidates() -> list[Path]:
    """Yield absolute libcairo paths to probe, Homebrew-aware first.

    Asks ``brew --prefix cairo`` when ``brew`` is on PATH so we pick up
    non-default prefixes (Apple Silicon, custom HOMEBREW_PREFIX, etc.).
    Falls back to a hardcoded list covering the common Homebrew and Linux
    distro locations.
    """
    seen: list[Path] = []
    brew = shutil.which("brew")
    if brew is not None:
        try:
            prefix = subprocess.check_output(
                [brew, "--prefix", "cairo"], text=True, stderr=subprocess.DEVNULL
            ).strip()
        except (subprocess.CalledProcessError, OSError):
            prefix = ""
        if prefix:
            seen.extend(Path(prefix) / "lib" / leaf for leaf in _LIBCAIRO_LEAFNAMES)
    for directory in _LIBCAIRO_FALLBACK_DIRS:
        seen.extend(Path(directory) / leaf for leaf in _LIBCAIRO_LEAFNAMES)
    return seen


_REEXEC_GUARD = "ELL_BUILD_LIBCAIRO_REEXECED"


def _ensure_libcairo_loadable() -> None:
    """Re-exec with ``DYLD_FALLBACK_LIBRARY_PATH`` set if needed (macOS only).

    miniforge/conda Pythons on macOS do not search ``/opt/homebrew`` by
    default, so even after ``brew install cairo`` cairocffi's ``dlopen``
    fails. ``ctypes.CDLL`` with an absolute path doesn't help either: dyld
    matches subsequent ``dlopen`` calls by ``install_name``, and Homebrew's
    libcairo records its full Cellar path. The only reliable fix is to put
    the directory on ``DYLD_FALLBACK_LIBRARY_PATH`` *before* dyld initialises
    — which means re-execing the interpreter. A guard env var prevents
    infinite loops if the re-exec still can't load the library.
    """
    if sys.platform != "darwin":
        return
    if os.environ.get(_REEXEC_GUARD) == "1":
        return
    if ctypes.util.find_library("cairo") is not None:
        return
    found = next((p for p in _libcairo_candidates() if p.is_file()), None)
    if found is None:
        return
    new_env = os.environ.copy()
    existing = new_env.get("DYLD_FALLBACK_LIBRARY_PATH", "")
    new_env["DYLD_FALLBACK_LIBRARY_PATH"] = (
        f"{found.parent}:{existing}" if existing else str(found.parent)
    )
    new_env[_REEXEC_GUARD] = "1"
    print(f"  re-execing with DYLD_FALLBACK_LIBRARY_PATH={found.parent} so cairo loads")
    os.execve(sys.executable, [sys.executable, *sys.argv], new_env)


def build_icon() -> None:
    """Render ``calibre-plugin/icon.svg`` to a 48 px ``images/icon.png``.

    Pip-installs ``cairosvg`` into ``build/_deps`` on demand if it is not
    already importable, so a clean checkout produces a real raster icon
    without manual setup. ``cairosvg`` needs the native ``libcairo`` library
    at runtime; :func:`_ensure_libcairo_loadable` runs early in :func:`main`
    and re-execs us with the right ``DYLD_FALLBACK_LIBRARY_PATH`` if dyld
    cannot find libcairo on its own. If even that fails we abort with a
    one-line install hint.
    """
    svg = PLUGIN / "icon.svg"
    out_dir = PLUGIN / "images"
    out_dir.mkdir(exist_ok=True)
    out = out_dir / "icon.png"
    if not svg.is_file():
        print("  icon: icon.svg missing, skipping")
        return
    if out.is_file():
        print(f"  icon: {out.relative_to(REPO)} already exists, skipping render")
        return
    _ensure_installed("cairosvg")
    try:
        cairosvg = importlib.import_module("cairosvg")
    except (OSError, ImportError) as exc:
        hint = _libcairo_install_hint()
        msg = f"cairosvg cannot load: {exc}\nInstall native deps with: {hint}"
        raise SystemExit(msg) from exc
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


_CALIBRE_CUSTOMIZE_FALLBACKS = (
    "/Applications/calibre.app/Contents/MacOS/calibre-customize",
    "/Applications/calibre.app/Contents/console.app/Contents/MacOS/calibre-customize",
)


def _calibre_customize() -> str | None:
    """Locate the ``calibre-customize`` binary, preferring the one on PATH."""
    found = shutil.which("calibre-customize")
    if found is not None:
        return found
    return next((p for p in _CALIBRE_CUSTOMIZE_FALLBACKS if Path(p).is_file()), None)


def install_into_calibre(plugin_zip: Path) -> int:
    """Hand ``plugin_zip`` to ``calibre-customize`` for installation.

    Calibre must be closed before running this — ``calibre-customize`` writes
    into ``~/Library/Preferences/calibre/plugins`` (macOS) or
    ``~/.config/calibre/plugins`` (Linux), and a running Calibre will not pick
    up the new bits until restart.
    """
    binary = _calibre_customize()
    if binary is None:
        print(
            "  install: 'calibre-customize' not found on PATH. "
            "On macOS, /Applications/calibre.app/Contents/MacOS/calibre-customize "
            "is the usual location.",
            file=sys.stderr,
        )
        return 1
    print(f"  install: {binary} --add-plugin {plugin_zip.relative_to(REPO)}")
    result = subprocess.run([binary, "--add-plugin", str(plugin_zip)], check=False)
    if result.returncode != 0:
        print(
            "  install: calibre-customize failed; make sure Calibre is fully quit before retrying.",
            file=sys.stderr,
        )
    return result.returncode


def main(argv: list[str] | None = None) -> int:
    """Run the full build and report the final zip path and size."""
    parser = argparse.ArgumentParser(
        description="Build (and optionally install) the Calibre plugin."
    )
    parser.add_argument(
        "--install",
        action="store_true",
        help=(
            "After building, register the zip with the local Calibre install via "
            "'calibre-customize --add-plugin'. Calibre must be closed first."
        ),
    )
    args = parser.parse_args(argv)

    _ensure_libcairo_loadable()
    print("Building Calibre plugin payload...")
    build_ell()
    build_ebooklib()
    build_simplemma()
    build_wordfreq()
    build_wordfreq_deps()
    build_icon()
    out = write_zip()
    size_mb = out.stat().st_size / (1024 * 1024)
    print(f"\nWrote {out.relative_to(REPO)} ({size_mb:.1f} MB)")
    if args.install:
        return install_into_calibre(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
