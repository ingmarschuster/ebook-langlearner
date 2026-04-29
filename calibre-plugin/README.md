# ebook-langlearner Calibre plugin

Adds a *Annotate for language learners* toolbar button to Calibre's library
view. Given a selected book with an EPUB format, the plugin runs the same
annotation pipeline as the CLI (`ebook-langlearner annotate`) and attaches
the result as a new EPUB format to the same library entry.

## Status

**Skeleton.** The file layout and Qt dialog compile and respect Calibre's
plugin conventions, but the vendored dependencies and the build script are
not yet wired. See the top-level `README.md` for the shipping CLI; this
directory is a design sketch.

## Layout

```
calibre-plugin/
├── __init__.py                  # InterfaceActionBase — plugin descriptor
├── action.py                    # InterfaceAction — toolbar/context entry + worker
├── ui.py                        # AnnotationDialog (Qt, via calibre's qt.core shim)
├── config.py                    # Per-user defaults (JSONConfig)
├── plugin-import-name-ell.txt   # Marker file — sets 'calibre_plugins.ell' namespace
├── ell/                         # Copy of src/ebook_langlearner (pipeline code + data)
└── vendor/                      # Populated at build time with ebooklib + simplemma
```

## Install (once built)

Calibre → *Preferences → Plugins → Load plugin from file* → select the zip
produced by `scripts/build_calibre_plugin.py`.

## Building

```bash
uv run python scripts/build_calibre_plugin.py
```

Produces `dist/ebook-langlearner-<version>.zip` (~15-20 MB) ready for
installation.

## Runtime dependencies

- **Bundled by Calibre:** `lxml`, `beautifulsoup4`, Qt.
- **Vendored by the build script:** `ebooklib`, `simplemma` (pruned to the
  9 supported languages).
- **Pre-aggregated into package data:** lemma- and surface-form frequencies
  (see `ell/data/`). `wordfreq` is not needed at runtime.
