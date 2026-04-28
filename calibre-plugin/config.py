"""Persisted per-user plugin configuration.

Calibre persists plugin config via :class:`calibre.utils.config.JSONConfig`;
we use it to remember the user's last source/target/level/format defaults.

This panel also hosts the dict.cc *index management* UI — building a SQLite
cache from a user-supplied TSV is a one-time per-language-pair action, so it
belongs in *Customize plugin*, not in the per-book annotation dialog. Once a
pair is indexed it is picked up automatically by
:func:`calibre_plugins.ell.action._annotate_job`.
"""

from __future__ import annotations

import sys
from pathlib import Path

from calibre.utils.config import JSONConfig
from qt.core import (
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

PREFS = JSONConfig("plugins/ebook_langlearner")
PREFS.defaults["source"] = "fr"
PREFS.defaults["target"] = "de"
PREFS.defaults["level"] = "b2"
PREFS.defaults["format"] = "ruby"

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


def _setup_vendor_path() -> None:
    """Make the plugin's vendored ``ell`` package importable.

    The settings panel needs the ``dictionaries`` module before any
    annotation has run, so we mirror :func:`action._setup_vendor_path` here
    rather than depend on the action module being loaded first.
    """
    vendor = str(Path(__file__).resolve().parent / "vendor")
    if Path(vendor).is_dir() and vendor not in sys.path:
        sys.path.insert(0, vendor)


class ConfigWidget(QWidget):
    """Widget shown by Calibre's *Customize plugin* dialog."""

    def __init__(self) -> None:
        """Build the form, seed defaults, and render the dict.cc index list."""
        super().__init__()
        outer = QVBoxLayout(self)

        defaults_box = QGroupBox("Defaults for the annotation dialog")
        form = QFormLayout(defaults_box)
        self.source = self._lang_combo(PREFS["source"])
        self.target = self._lang_combo(PREFS["target"])
        self.level = QComboBox()
        for level in ("a1", "a2", "b1", "b2", "c1", "c2"):
            self.level.addItem(level.upper(), level)
        self.level.setCurrentText(PREFS["level"].upper())
        form.addRow("Default source language:", self.source)
        form.addRow("Default target language:", self.target)
        form.addRow("Default CEFR level:", self.level)
        outer.addWidget(defaults_box)

        outer.addWidget(self._build_dictcc_panel())

    def _lang_combo(self, current: str) -> QComboBox:
        """Build a language combobox preselected to ``current``."""
        combo = QComboBox()
        for code, name in _SUPPORTED_LANGUAGES:
            combo.addItem(f"{code} — {name}", code)
        for index in range(combo.count()):
            if combo.itemData(index) == current:
                combo.setCurrentIndex(index)
                break
        return combo

    def _build_dictcc_panel(self) -> QGroupBox:
        """Compose the dict.cc index management group.

        Shows the list of currently cached ``(source, target)`` pairs, an
        Add row that builds a new index from a TSV file, and a Remove
        button to drop a stale index.
        """
        box = QGroupBox("dict.cc dictionaries (optional, higher-quality translations)")
        layout = QVBoxLayout(box)

        layout.addWidget(
            QLabel(
                "Built indexes are cached and reused automatically when annotating "
                "matching language pairs."
            )
        )

        self.indexed_list = QListWidget()
        self._refresh_index_list()
        layout.addWidget(self.indexed_list)

        remove_row = QHBoxLayout()
        self.remove_button = QPushButton("Remove selected")
        self.remove_button.clicked.connect(self._on_remove_index)
        remove_row.addWidget(self.remove_button)
        remove_row.addStretch(1)
        layout.addLayout(remove_row)

        layout.addWidget(QLabel("Build a new index from a dict.cc TSV export:"))

        add_row = QHBoxLayout()
        self.new_source = self._lang_combo(PREFS["source"])
        self.new_target = self._lang_combo(PREFS["target"])
        add_row.addWidget(QLabel("From:"))
        add_row.addWidget(self.new_source)
        add_row.addWidget(QLabel("To:"))
        add_row.addWidget(self.new_target)
        layout.addLayout(add_row)

        file_row = QHBoxLayout()
        self.new_tsv = QLineEdit()
        self.new_tsv.setPlaceholderText("Path to a dict.cc *.txt or *.tsv export")
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._on_pick_tsv)
        file_row.addWidget(self.new_tsv, 1)
        file_row.addWidget(browse)
        layout.addLayout(file_row)

        build_row = QHBoxLayout()
        build_button = QPushButton("Build index")
        build_button.clicked.connect(self._on_build_index)
        self.build_status = QLabel("")
        build_row.addWidget(build_button)
        build_row.addWidget(self.build_status, 1)
        layout.addLayout(build_row)

        return box

    def _refresh_index_list(self) -> None:
        """Repopulate the ``indexed_list`` widget from the on-disk cache."""
        from calibre_plugins.ell.ell.dictionaries.dictcc import (
            dictcc_index_path_for,
            list_indexed_dictcc_pairs,
        )

        self.indexed_list.clear()
        for src, tgt in list_indexed_dictcc_pairs():
            label = f"{src} → {tgt}    {dictcc_index_path_for(src, tgt)}"
            item = QListWidgetItem(label)
            item.setData(0x0100, (src, tgt))
            self.indexed_list.addItem(item)

    def _on_pick_tsv(self) -> None:
        """File picker handler for the *Browse…* button."""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select dict.cc export", "", "TSV files (*.txt *.tsv);;All files (*)"
        )
        if path:
            self.new_tsv.setText(path)

    def _on_build_index(self) -> None:
        """Ingest the chosen TSV into the per-pair SQLite cache.

        Runs synchronously in the GUI thread; a typical dict.cc export
        parses in a couple of seconds, fast enough that wiring up a worker
        thread would add more risk than it removes.
        """
        _setup_vendor_path()
        from calibre_plugins.ell.ell.dictionaries.dictcc import build_dictcc_index

        tsv = self.new_tsv.text().strip()
        if not tsv:
            self.build_status.setText("Pick a TSV file first.")
            return
        path = Path(tsv)
        if not path.is_file():
            self.build_status.setText(f"Not a file: {path}")
            return
        source = self.new_source.currentData()
        target = self.new_target.currentData()
        if source == target:
            self.build_status.setText("Source and target must differ.")
            return
        self.build_status.setText("Building…")
        self.build_status.repaint()
        index = build_dictcc_index(path, source, target)
        self.build_status.setText(f"Built {index.name}")
        self._refresh_index_list()

    def _on_remove_index(self) -> None:
        """Delete the SQLite cache for the selected ``(source, target)`` pair."""
        _setup_vendor_path()
        from calibre_plugins.ell.ell.dictionaries.dictcc import dictcc_index_path_for

        item = self.indexed_list.currentItem()
        if item is None:
            return
        source, target = item.data(0x0100)
        confirm = QMessageBox.question(
            self,
            "Remove dict.cc index",
            f"Delete the cached dict.cc index for {source} → {target}?",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return
        path = dictcc_index_path_for(source, target)
        if path.exists():
            path.unlink()
        self._refresh_index_list()

    def save_settings(self) -> None:
        """Persist the current widget values back to :data:`PREFS`."""
        PREFS["source"] = self.source.currentData()
        PREFS["target"] = self.target.currentData()
        PREFS["level"] = self.level.currentData()
