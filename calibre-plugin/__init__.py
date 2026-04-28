"""Calibre plugin entry point for ebook-langlearner.

Registers an :class:`InterfaceActionBase` so a toolbar/context-menu action
can open the annotation dialog. The actual action class lives in
:mod:`calibre_plugins.ell.action` — Calibre loads plugins under the
``calibre_plugins.<name>`` namespace, where ``<name>`` comes from the
``plugin-import-name-<name>.txt`` marker file shipped alongside this module.

Calibre discovers this plugin by loading the zip produced by
``scripts/build_calibre_plugin.py`` via *Preferences → Plugins → Load
plugin from file*.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from calibre.customize import InterfaceActionBase

if TYPE_CHECKING:
    from calibre_plugins.ell.config import ConfigWidget
    from qt.core import QWidget


class EbookLangLearnerPlugin(InterfaceActionBase):
    """Plugin descriptor.

    Calibre instantiates this class once at startup to read ``name``,
    ``author``, ``version`` etc.; the actual UI action is constructed
    lazily via :meth:`load_actual_plugin`.
    """

    name = "ebook-langlearner"
    description = "Annotate rare words in EPUB files with inline translations."
    supported_platforms: ClassVar[list[str]] = ["windows", "osx", "linux"]
    author = "Ingmar Schuster"
    version = (0, 1, 1)
    minimum_calibre_version = (6, 0, 0)

    actual_plugin = "calibre_plugins.ell.action:EbookLangLearnerAction"

    def is_customizable(self) -> bool:
        """Enable the *Customize plugin* button so defaults can be configured."""
        return True

    def config_widget(self) -> QWidget:
        """Return the Qt config widget shown in *Customize plugin*.

        Constructed lazily so Qt isn't imported at plugin discovery time
        (Calibre imports every plugin's ``__init__`` at startup to read
        metadata).
        """
        from calibre_plugins.ell.config import ConfigWidget

        return ConfigWidget()

    def save_settings(self, config_widget: ConfigWidget) -> None:
        """Persist the values entered in :meth:`config_widget`."""
        config_widget.save_settings()
