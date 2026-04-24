"""Persisted per-user plugin configuration.

Calibre persists plugin config via :class:`calibre.utils.config.JSONConfig`;
we use it to remember the user's last source/target/level/dict.cc path so
repeated runs on multiple books don't require re-entering the same fields.
"""

from __future__ import annotations

from calibre.utils.config import JSONConfig
from qt.core import QComboBox, QFormLayout, QLineEdit, QWidget

PREFS = JSONConfig("plugins/ebook_langlearner")
PREFS.defaults["source"] = "fr"
PREFS.defaults["target"] = "de"
PREFS.defaults["level"] = "b2"
PREFS.defaults["format"] = "ruby"
PREFS.defaults["dictcc_path"] = ""


class ConfigWidget(QWidget):
    """Widget shown by Calibre's *Customize plugin* dialog."""

    def __init__(self) -> None:
        """Build the form and seed it from :data:`PREFS`."""
        super().__init__()
        layout = QFormLayout(self)

        self.source = QLineEdit(PREFS["source"])
        self.target = QLineEdit(PREFS["target"])
        self.level = QComboBox()
        for level in ("a1", "a2", "b1", "b2", "c1", "c2"):
            self.level.addItem(level.upper(), level)
        self.level.setCurrentText(PREFS["level"].upper())
        self.dictcc = QLineEdit(PREFS["dictcc_path"])

        layout.addRow("Default source language:", self.source)
        layout.addRow("Default target language:", self.target)
        layout.addRow("Default CEFR level:", self.level)
        layout.addRow("Default dict.cc TSV:", self.dictcc)

    def save_settings(self) -> None:
        """Persist the current widget values back to :data:`PREFS`."""
        PREFS["source"] = self.source.text().strip().lower()
        PREFS["target"] = self.target.text().strip().lower()
        PREFS["level"] = self.level.currentData()
        PREFS["dictcc_path"] = self.dictcc.text().strip()
