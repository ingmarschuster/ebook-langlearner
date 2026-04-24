"""Qt dialog for the annotation action.

Prompts the user for source/target language, CEFR level, annotation format,
and a dict.cc TSV file path. Returns the selection as a dict consumed by
:func:`calibre_plugins.ell.action._annotate_job`.

Uses Calibre's ``qt.core`` shim so the same source works on both Qt5 and
Qt6 Calibre builds.
"""

from __future__ import annotations

from qt.core import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
    QWidget,
)


class AnnotationDialog(QDialog):
    """Modal dialog collecting annotation parameters."""

    def __init__(self, parent: QWidget, epub_path) -> None:  # noqa: ANN001
        """Build the dialog for ``epub_path`` (shown in the title)."""
        super().__init__(parent)
        self.setWindowTitle(f"Annotate: {epub_path.name}")

        layout = QVBoxLayout(self)
        form = QFormLayout()

        self.source = QComboBox()
        self.target = QComboBox()
        for code, name in _SUPPORTED_LANGUAGES:
            self.source.addItem(f"{code} — {name}", code)
            self.target.addItem(f"{code} — {name}", code)
        self.source.setCurrentIndex(_index_of("fr"))
        self.target.setCurrentIndex(_index_of("de"))

        self.level = QComboBox()
        for level in ("A1", "A2", "B1", "B2", "C1", "C2"):
            self.level.addItem(level, level.lower())
        self.level.setCurrentText("B2")

        self.fmt = QComboBox()
        self.fmt.addItem("Ruby (above the word)", "ruby")
        self.fmt.addItem("Parenthetical (inline)", "parenthetical")

        self.dictcc = QLineEdit()
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._pick_dictcc)
        dictcc_row = QHBoxLayout()
        dictcc_row.addWidget(self.dictcc, 1)
        dictcc_row.addWidget(browse)
        dictcc_container = QWidget()
        dictcc_container.setLayout(dictcc_row)

        form.addRow("From:", self.source)
        form.addRow("To:", self.target)
        form.addRow("CEFR level:", self.level)
        form.addRow("Format:", self.fmt)
        form.addRow("dict.cc TSV:", dictcc_container)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _pick_dictcc(self) -> None:
        """Open a file picker for the dict.cc TSV export."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select dict.cc export", "", "TSV files (*.txt *.tsv);;All files (*)"
        )
        if path:
            self.dictcc.setText(path)

    def result_config(self) -> dict:
        """Return the dialog selection as a plain dict the worker can consume."""
        return {
            "source": self.source.currentData(),
            "target": self.target.currentData(),
            "level": self.level.currentData(),
            "format": self.fmt.currentData(),
            "dictcc_path": self.dictcc.text(),
        }


_SUPPORTED_LANGUAGES: tuple[tuple[str, str], ...] = (
    ("de", "German"),
    ("en", "English"),
    ("es", "Spanish"),
    ("fr", "French"),
    ("it", "Italian"),
    ("nl", "Dutch"),
    ("pl", "Polish"),
    ("pt", "Portuguese"),
    ("sv", "Swedish"),
)


def _index_of(code: str) -> int:
    """Index of ``code`` in :data:`_SUPPORTED_LANGUAGES`; used to preselect defaults."""
    for index, (lang_code, _) in enumerate(_SUPPORTED_LANGUAGES):
        if lang_code == code:
            return index
    return 0
