"""Library-view action: annotate, switch level, or strip annotations.

This is the runtime :class:`InterfaceAction` Calibre wires up when the user
adds the plugin. The toolbar button opens a small menu with three entries:

* **Annotate** — opens the annotation dialog and runs the pipeline on a
  worker thread; the result is added to the library as a new book entry.
* **Change visible level…** — switches the visible CEFR level of an
  already-annotated EPUB by rewriting only the active-level CSS block;
  replaces the EPUB format on the same book.
* **Strip annotations** — removes every annotation from the selected book
  and replaces its EPUB format with the cleaned copy.
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
        None,
        "Annotate, switch level, or strip annotations on the selected book",
        None,
    )
    action_type = "current"

    def genesis(self) -> None:
        """Build the toolbar menu, load the plugin icon, and wire handlers.

        ``action_spec``'s icon slot only resolves Calibre's built-in icon
        names (via ``I(...)``); custom plugin icons must be loaded from the
        zip via ``get_icons``. We do that here and call ``setIcon`` on the
        toolbar action so the toolbar/menu entry actually shows the glyph.
        """
        from calibre_plugins.ell import get_icons
        from qt.core import QMenu

        icon = get_icons("images/icon.png")
        if icon is not None and not icon.isNull():
            self.qaction.setIcon(icon)

        menu = QMenu(self.gui)
        annotate = menu.addAction("Annotate…")
        annotate.triggered.connect(self.open_dialog)
        set_level = menu.addAction("Change visible level…")
        set_level.triggered.connect(self.open_set_level)
        strip = menu.addAction("Strip annotations")
        strip.triggered.connect(self.open_strip)
        self.qaction.setMenu(menu)
        # Default click (no menu pop) runs the most common action.
        self.qaction.triggered.connect(self.open_dialog)

    def _selected_epub(self) -> tuple[int, Path] | None:
        """Return ``(book_id, epub_path)`` for the selected book, or warn and return ``None``."""
        from calibre.gui2 import error_dialog

        rows = self.gui.library_view.selectionModel().selectedRows()
        if not rows:
            error_dialog(
                self.gui,
                "No book selected",
                "Select a book with an EPUB format first.",
                show=True,
            )
            return None

        book_id = self.gui.library_view.model().id(rows[0])
        db = self.gui.current_db.new_api
        abs_path = db.format_abspath(book_id, "EPUB")
        if not abs_path:
            error_dialog(
                self.gui,
                "No EPUB format",
                "The selected book has no EPUB format.",
                show=True,
            )
            return None
        return book_id, Path(abs_path)

    def open_dialog(self) -> None:
        """Collect the selected book, open the annotation dialog, run the pipeline."""
        from calibre_plugins.ell.ui import AnnotationDialog

        selection = self._selected_epub()
        if selection is None:
            return
        book_id, epub_path = selection

        dialog = AnnotationDialog(self.gui, epub_path)
        if dialog.exec() != dialog.DialogCode.Accepted:
            return

        self._run_annotate_job(book_id, epub_path, dialog.result_config())

    def open_set_level(self) -> None:
        """Prompt for a CEFR level and rewrite the EPUB's active-level block."""
        from qt.core import QInputDialog

        selection = self._selected_epub()
        if selection is None:
            return
        book_id, epub_path = selection

        levels = ("A1", "A2", "B1", "B2", "C1", "C2")
        level, ok = QInputDialog.getItem(
            self.gui,
            "Change visible level",
            "Visible CEFR level:",
            list(levels),
            editable=False,
        )
        if not ok or not level:
            return
        self._run_set_level_job(book_id, epub_path, level)

    def open_strip(self) -> None:
        """Strip every annotation from the selected book."""
        from calibre.gui2 import question_dialog

        selection = self._selected_epub()
        if selection is None:
            return
        book_id, epub_path = selection

        confirm = question_dialog(
            self.gui,
            "Strip annotations",
            "Remove every annotation from this book? The EPUB format will be replaced.",
        )
        if not confirm:
            return
        self._run_strip_job(book_id, epub_path)

    def _run_annotate_job(self, book_id: int, input_epub: Path, config: dict) -> None:
        """Queue annotation as a Calibre background job."""
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
        job.kind = "annotate"
        job.book_id = book_id
        job.config = config
        self.gui.job_manager.run_threaded_job(job)

    def _run_set_level_job(self, book_id: int, input_epub: Path, level: str) -> None:
        """Queue an active-level rewrite as a background job."""
        from calibre.gui2.threaded_jobs import ThreadedJob

        job = ThreadedJob(
            "ebook_langlearner_set_level",
            f"Switching visible level to {level} on {input_epub.name}",
            _set_level_job,
            (input_epub, level),
            {},
            self._job_done,
            killable=False,
        )
        job.kind = "set_level"
        job.book_id = book_id
        job.level = level
        self.gui.job_manager.run_threaded_job(job)

    def _run_strip_job(self, book_id: int, input_epub: Path) -> None:
        """Queue a strip-annotations job."""
        from calibre.gui2.threaded_jobs import ThreadedJob

        job = ThreadedJob(
            "ebook_langlearner_strip",
            f"Stripping annotations from {input_epub.name}",
            _strip_job,
            (input_epub,),
            {},
            self._job_done,
            killable=False,
        )
        job.kind = "strip"
        job.book_id = book_id
        self.gui.job_manager.run_threaded_job(job)

    def _job_done(self, job: ThreadedJob) -> None:
        """Dispatch on ``job.kind`` and update the library accordingly."""
        if job.failed:
            self.gui.job_exception(job, dialog_title=f"{job.kind} failed".capitalize())
            return

        output_path: Path = job.result
        if job.kind == "annotate":
            self._on_annotate_done(job, output_path)
        else:
            # set-level and strip are in-place operations from the user's
            # perspective: replace the EPUB format on the existing book.
            db = self.gui.current_db.new_api
            db.add_format(job.book_id, "EPUB", str(output_path), replace=True)
            self.gui.library_view.model().refresh_ids([job.book_id])

    def _on_annotate_done(self, job: ThreadedJob, output_path: Path) -> None:
        """Add the freshly-annotated EPUB as a new library entry.

        Adding it as a *new* entry (rather than overwriting the original
        EPUB format) preserves the unannotated source and surfaces the
        annotated copy as its own item in the library view, matching
        user expectations for "process this book".
        """
        config: dict = job.config
        db = self.gui.current_db.new_api
        mi = db.get_metadata(job.book_id, get_cover=True, cover_as_data=True)
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


def _set_level_job(
    input_epub: Path,
    level: str,
    log: Any,
    abort: Any,
    notifications: Any,
) -> Path:
    """Rewrite the active-level CSS block on a worker thread."""
    del abort, notifications
    _setup_vendor_path()

    from calibre_plugins.ell.ell.epub_pipeline import set_visible_level

    output_path = input_epub.with_suffix(f".{level.lower()}.epub")
    log(f"Switching visible level to {level} → {output_path}")
    set_visible_level(input_epub, output_path, level)
    return output_path


def _strip_job(
    input_epub: Path,
    log: Any,
    abort: Any,
    notifications: Any,
) -> Path:
    """Strip every annotation on a worker thread."""
    del abort, notifications
    _setup_vendor_path()

    from calibre_plugins.ell.ell.epub_pipeline import strip_annotations

    output_path = input_epub.with_suffix(".stripped.epub")
    stats = strip_annotations(input_epub, output_path)
    log(
        f"Stripped {stats.annotations_removed} annotations across "
        f"{stats.documents_processed} documents → {output_path}"
    )
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
