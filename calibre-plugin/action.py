"""Library-view action: annotate a selected EPUB.

This is the runtime :class:`InterfaceAction` Calibre wires up when the user
adds the plugin. It adds a toolbar button (and context-menu entry) that
opens the annotation dialog for the currently selected book, writes the
annotated EPUB to the library as a new format, and shows progress in
Calibre's job panel so long runs don't block the UI.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from calibre.gui2.actions import InterfaceAction

if TYPE_CHECKING:
    from pathlib import Path


class EbookLangLearnerAction(InterfaceAction):
    """Toolbar/context-menu entry point."""

    name = "ebook-langlearner"
    action_spec = ("Annotate for language learners", None, "Add inline translations for rare words", None)
    action_type = "current"

    def genesis(self) -> None:
        """Wire the toolbar click to :meth:`open_dialog` (called by Calibre once)."""
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
        epub_path = db.format_abspath(book_id, "EPUB")
        if not epub_path:
            from calibre.gui2 import error_dialog

            error_dialog(
                self.gui,
                "No EPUB format",
                "The selected book has no EPUB format to annotate.",
                show=True,
            )
            return

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
            book_id=book_id,
        )
        self.gui.job_manager.run_threaded_job(job)

    def _job_done(self, job) -> None:  # noqa: ANN001 — Calibre Job object is opaque
        """Attach the annotated EPUB back to the book as a new format."""
        if job.failed:
            self.gui.job_exception(job, dialog_title="Annotation failed")
            return
        output_path = job.result
        book_id = job.book_id
        db = self.gui.current_db.new_api
        db.add_format(book_id, "EPUB", str(output_path), replace=False)
        self.gui.library_view.model().refresh_ids([book_id])


def _annotate_job(input_epub: Path, config: dict, log, abort, notifications) -> Path:  # noqa: ANN001, ARG001
    """Run the annotation pipeline on a worker thread.

    The bundled :mod:`ell` package (the project's ``src/ebook_langlearner``
    copied into the plugin zip) is imported lazily here so the plugin
    import cost at Calibre startup stays near zero.
    """
    from calibre_plugins.ell.ell.annotate import AnnotationConfig, Annotator
    from calibre_plugins.ell.ell.cefr import cefr_cutoff
    from calibre_plugins.ell.ell.dictionaries import DictCCDictionary
    from calibre_plugins.ell.ell.epub_pipeline import annotate_epub
    from calibre_plugins.ell.ell.render import AnnotationFormat

    cutoff = cefr_cutoff(config["source"], config["level"])
    dictionary = DictCCDictionary.from_file(
        config["dictcc_path"], config["source"], config["target"]
    )
    annotator = Annotator(
        dictionary,
        AnnotationConfig(
            source_lang=config["source"],
            target_lang=config["target"],
            cutoff=cutoff,
            fmt=AnnotationFormat(config["format"]),
        ),
    )
    output_path = input_epub.with_suffix(f".{config['level']}.annotated.epub")
    annotate_epub(input_epub, output_path, annotator)
    return output_path
