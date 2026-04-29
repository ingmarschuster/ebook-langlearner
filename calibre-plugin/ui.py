"""Qt dialog for the annotation action.

Prompts the user for source/target language, CEFR level, annotation format,
and the ruby font-size percent. Returns the selection as a dict consumed by
:func:`calibre_plugins.ell.action._annotate_job`.

dict.cc dictionaries are no longer chosen here — they are ingested once via
the plugin's *Customize plugin* settings panel and looked up automatically
by ``(source, target)`` at annotation time.

Uses Calibre's ``qt.core`` shim so the same source works on both Qt5 and
Qt6 Calibre builds.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from qt.core import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QDoubleSpinBox,
    QFormLayout,
    QVBoxLayout,
    QWidget,
)

if TYPE_CHECKING:
    from pathlib import Path

DEFAULT_RUBY_FONT_PCT = 90.0
"""Default ruby font-size percent. Mirrors the CLI default — kept inline so
this module stays import-safe before the vendored ``ell`` package is on
``sys.path``."""

DEFAULT_ANNOTATION_GREY_PCT = 80.0
"""Default annotation text darkness percent (100=black, 0=white). Min 50."""


class AnnotationDialog(QDialog):
    """Modal dialog collecting annotation parameters."""

    def __init__(self, parent: QWidget, epub_path: Path) -> None:
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

        self.ruby_font_pct = QDoubleSpinBox()
        self.ruby_font_pct.setRange(50.0, 120.0)
        self.ruby_font_pct.setDecimals(0)
        self.ruby_font_pct.setSingleStep(5.0)
        self.ruby_font_pct.setSuffix(" %")
        self.ruby_font_pct.setValue(DEFAULT_RUBY_FONT_PCT)
        self.ruby_font_pct.setToolTip(
            "Ruby translation font-size as a percentage of the base word's font-size."
        )

        self.annotation_grey_pct = QDoubleSpinBox()
        self.annotation_grey_pct.setRange(50.0, 100.0)
        self.annotation_grey_pct.setDecimals(0)
        self.annotation_grey_pct.setSingleStep(5.0)
        self.annotation_grey_pct.setSuffix(" %")
        self.annotation_grey_pct.setValue(DEFAULT_ANNOTATION_GREY_PCT)
        self.annotation_grey_pct.setToolTip(
            "Annotation text darkness: 100% = black, 50% = mid-grey."
        )

        form.addRow("From:", self.source)
        form.addRow("To:", self.target)
        form.addRow("CEFR level:", self.level)
        form.addRow("Format:", self.fmt)
        form.addRow("Ruby font size:", self.ruby_font_pct)
        form.addRow("Annotation grey %:", self.annotation_grey_pct)
        layout.addLayout(form)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def result_config(self) -> dict:
        """Return the dialog selection as a plain dict the worker can consume."""
        return {
            "source": self.source.currentData(),
            "target": self.target.currentData(),
            "level": self.level.currentData(),
            "format": self.fmt.currentData(),
            "ruby_font_pct": float(self.ruby_font_pct.value()),
            "annotation_grey_pct": float(self.annotation_grey_pct.value()),
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
