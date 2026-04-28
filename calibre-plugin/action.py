"""Library-view action: annotate a selected EPUB.

This is the runtime :class:`InterfaceAction` Calibre wires up when the user
adds the plugin. It adds a toolbar button (and context-menu entry) that
opens the annotation dialog for the currently selected book, runs the
annotation as a background job, and adds the result as a new book entry
in the library.
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import TYPE_CHECKING

from calibre.gui2.actions import InterfaceAction

if TYPE_CHECKING:
    from typing import Any

    from calibre.gui2.threaded_jobs import ThreadedJob


def _setup_vendor_path() -> None:
    """Prepend the plugin's ``vendor/`` directory to ``sys.path``.

    The annotation pipeline imports ``ebooklib``, ``simplemma`` and
    ``wordfreq`` as top-level packages; those are vendored inside the
    plugin zip but Calibre's plugin import hook only resolves the
    ``calibre_plugins.<name>.*`` namespace, not arbitrary subdirs. This
    inserts ``vendor/`` once so the absolute imports inside ``ell/`` keep
    working unmodified — the source ships unforked between CLI and plugin.
    """
    vendor_dir = str(Path(__file__).resolve().parent / "vendor")
    if Path(vendor_dir).is_dir() and vendor_dir not in sys.path:
        sys.path.insert(0, vendor_dir)


class EbookLangLearnerAction(InterfaceAction):
    """Toolbar/context-menu entry point."""

    name = "ebook-langlearner"
    action_spec = (
        "Annotate for language learners",
        "images/icon.png",
        "Add inline translations for rare words",
        None,
    )
    action_type = "current"

    def genesis(self) -> None:
        """Wire the toolbar click to :meth:`open_dialog`.

        The icon path in :attr:`action_spec` is resolved by Calibre's
        plugin loader against the zip root, so no manual icon loading is
        needed here.
        """
        self.qaction.triggered.connect(self.open_dialog)

    def open_dialog(self) -> None:
        """Collect the selected book, open the dialog, run the pipeline."""
        from calibre_plugins.ell.ui import AnnotationDialog

        rows = self.gui.library_view.selectionModel().selectedRows()
        if not rows:
            from calibre.gui2 import error_dialog

            error_dialog(
                self.gui,
                "No book selected",
                "Select a book with an EPUB format first.",
                show=True,
            )
            return

        book_id = self.gui.library_view.model().id(rows[0])
        db = self.gui.current_db.new_api
        abs_path = db.format_abspath(book_id, "EPUB")
        if not abs_path:
            from calibre.gui2 import error_dialog

            error_dialog(
                self.gui,
                "No EPUB format",
                "The selected book has no EPUB format to annotate.",
                show=True,
            )
            return
        epub_path = Path(abs_path)

        dialog = AnnotationDialog(self.gui, epub_path)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        self._run_job(book_id, epub_path, dialog.result_config())

    def _run_job(self, book_id: int, input_epub: Path, config: dict) -> None:
        """Queue the annotation as a Calibre background job.

        Calibre's job manager handles progress reporting and cancellation;
        keeping the annotation off the UI thread matters because long books
        can take 30+ seconds to annotate.
        """
        from calibre.gui2.threaded_jobs import ThreadedJob

        job = ThreadedJob(
            "ebook_langlearner_annotate",
            f"Annotating {input_epub.name}",
            _annotate_job,
            (input_epub, config),
            {},
            self._job_done,
            killable=False,
        )
        job.book_id = book_id
        job.config = config
        self.gui.job_manager.run_threaded_job(job)

    def _job_done(self, job: ThreadedJob) -> None:
        """Add the annotated EPUB to the library as a new book entry.

        Adding it as a *new* entry (rather than overwriting the original
        EPUB format on the source book) preserves the unannotated source
        and surfaces the annotated copy as its own item in the library
        view, which matches user expectations for "process this book".
        """
        if job.failed:
            self.gui.job_exception(job, dialog_title="Annotation failed")
            return

        output_path: Path = job.result
        source_book_id: int = job.book_id
        config: dict = job.config

        db = self.gui.current_db.new_api
        mi = db.get_metadata(source_book_id, get_cover=True, cover_as_data=True)
        suffix = f"({config['level'].upper()} {config['source']}→{config['target']})"
        mi.title = f"{mi.title} {suffix}"
        new_id = db.create_book_entry(mi, add_duplicates=True)
        db.add_format(new_id, "EPUB", str(output_path), replace=True)
        self.gui.library_view.model().books_added(1)
        self.gui.library_view.model().refresh_ids([new_id])


def _annotate_job(
    input_epub: Path,
    config: dict,
    log: Any,
    abort: Any,
    notifications: Any,
) -> Path:
    """Run the annotation pipeline on a worker thread.

    Sets up the vendor import path before importing the bundled ``ell``
    pipeline so its absolute imports (``ebooklib``, ``simplemma``,
    ``wordfreq``) resolve to the vendored copies inside the plugin zip.

    ``log``, ``abort``, and ``notifications`` are passed positionally by
    Calibre's :class:`ThreadedJob` machinery; this pipeline doesn't surface
    progress, so they are accepted but unused.
    """
    del abort
    _setup_vendor_path()

    from calibre_plugins.ell.ell.annotate import AnnotationConfig, Annotator
    from calibre_plugins.ell.ell.cefr import cefr_cutoff
    from calibre_plugins.ell.ell.dictionaries import (
        CompositeDictionary,
        DictCCIndex,
        WiktionaryDictionary,
    )
    from calibre_plugins.ell.ell.dictionaries.download import ensure_wiktionary_index
    from calibre_plugins.ell.ell.epub_pipeline import annotate_epub
    from calibre_plugins.ell.ell.render import AnnotationFormat

    source = config["source"]
    target = config["target"]
    # The plugin annotates down to the A1 cutoff so a single book can serve
    # readers at any level; the dialog's "level" selection only controls the
    # initial visible level baked into the stylesheet.
    cutoff = cefr_cutoff(source, "A1")
    active_level = str(config["level"]).upper()

    backends: list = []
    cached_dictcc = DictCCIndex(source, target)
    if cached_dictcc.is_available:
        log(f"Using cached dict.cc index ({source} → {target}) at {cached_dictcc.index_path}")
        backends.append(cached_dictcc)
    else:
        log(f"No cached dict.cc index for {source} → {target}; ensuring Wiktionary fallback")

        def _on_progress(stage: str, current: int, total: int | None) -> None:
            _report_download_progress(notifications, log, stage, current, total)

        ensure_wiktionary_index(source, progress=_on_progress)
        backends.append(WiktionaryDictionary(source))

    dictionary = backends[0] if len(backends) == 1 else CompositeDictionary(backends)

    annotator = Annotator(
        dictionary,
        AnnotationConfig(
            source_lang=source,
            target_lang=target,
            cutoff=cutoff,
            fmt=AnnotationFormat(config["format"]),
            ruby_font_pct=float(config["ruby_font_pct"]),
            active_level=active_level,
        ),
    )
    output_path = input_epub.with_suffix(f".{config['level']}.annotated.epub")
    annotate_epub(input_epub, output_path, annotator)
    return output_path


def _report_download_progress(
    notifications: Any,
    log: Any,
    stage: str,
    current: int,
    total: int | None,
) -> None:
    """Forward Kaikki download progress to Calibre's job UI.

    ``notifications`` is a queue-like callable that takes
    ``(percent, message)``. We report integer percent during downloading
    and a static "indexing" line during the SQLite build (which has no
    natural percent — Calibre will animate the progress bar instead).
    """
    if stage == "indexing":
        notifications((1.0, "Indexing Wiktionary dump…"))
        log("Indexing Wiktionary dump into SQLite…")
        return
    if total:
        fraction = current / total
        notifications(
            (
                fraction,
                f"Downloading Wiktionary: {current / 1_048_576:.0f} / {total / 1_048_576:.0f} MiB",
            )
        )
    else:
        notifications((0.0, f"Downloading Wiktionary: {current / 1_048_576:.0f} MiB"))
