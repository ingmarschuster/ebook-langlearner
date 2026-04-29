"""End-to-end EPUB annotation pipeline.

Reads an EPUB with :mod:`ebooklib`, walks every XHTML content document, and
for each text node that isn't inside a "do not touch" ancestor (ruby, script,
style, code, pre, kbd, anchor) passes the text through :class:`Annotator` and
replaces the text node with the resulting HTML fragment. A shared stylesheet
is added so ruby annotations render consistently across readers.
"""

from __future__ import annotations

from dataclasses import dataclass
from html import escape as html_escape
from pathlib import PurePosixPath
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup, NavigableString, Tag
from ebooklib import ITEM_DOCUMENT, epub

from .render import (
    BEGIN_LEVEL_MARKER_PREFIX,
    BEGIN_LEVEL_MARKER_SUFFIX,
    END_LEVEL_MARKER,
    build_active_level_block,
    build_annotation_css,
)

if TYPE_CHECKING:
    from collections.abc import Iterator
    from pathlib import Path

    from .annotate import Annotator

SKIP_PARENTS = frozenset({"ruby", "rt", "rp", "script", "style", "code", "pre", "kbd", "a"})
"""Tag names whose descendant text must not be annotated.

* ``ruby``/``rt``/``rp``: already-annotated content (don't double-wrap).
* ``script``/``style``: not prose.
* ``code``/``pre``/``kbd``: technical content preserved verbatim.
* ``a``: hyperlinks — annotating inside them confuses the link target.
"""


@dataclass
class PipelineStats:
    """Counters populated as the pipeline runs, returned to callers.

    Attributes:
        documents_processed: Number of XHTML content documents visited.
        text_nodes_processed: Number of text nodes whose content changed (i.e.
            at least one rare word was annotated).
    """

    documents_processed: int = 0
    text_nodes_processed: int = 0


def annotate_epub(
    source: Path | str,
    destination: Path | str,
    annotator: Annotator,
) -> PipelineStats:
    """Annotate an EPUB end-to-end.

    Args:
        source: Path to the input ``.epub`` file.
        destination: Path where the annotated EPUB will be written. If the
            file exists it is overwritten.
        annotator: The configured :class:`Annotator` to use.

    Returns:
        Counters summarizing the run.
    """
    book = epub.read_epub(str(source))
    stats = PipelineStats()

    for item in list(book.get_items_of_type(ITEM_DOCUMENT)):
        original_html = item.get_content().decode("utf-8")
        annotated_html = _annotate_document(original_html, annotator, stats)
        item.set_content(annotated_html.encode("utf-8"))
        _register_stylesheet_link(item)
        stats.documents_processed += 1

    _add_stylesheet(
        book,
        ruby_font_pct=annotator.config.ruby_font_pct,
        active_level=annotator.config.active_level,
        annotation_grey_pct=annotator.config.annotation_grey_pct,
    )
    epub.write_epub(str(destination), book)
    return stats


def _annotate_document(html: str, annotator: Annotator, stats: PipelineStats) -> str:
    """Parse a single XHTML document, annotate its text nodes, and serialize.

    Text nodes under any ancestor listed in :data:`SKIP_PARENTS` are left
    untouched so we never annotate inside existing ruby, links, or code blocks.
    """
    soup = BeautifulSoup(html, "lxml-xml")
    for text_node in list(_iter_text_nodes(soup)):
        parent_chain = _parent_chain(text_node)
        if any(name in SKIP_PARENTS for name in parent_chain):
            continue
        text = str(text_node)
        if not text.strip():
            continue
        annotated_fragment = annotator.annotate_text(text)
        if annotated_fragment == html_escape(text):
            continue
        _replace_with_html(text_node, annotated_fragment)
        stats.text_nodes_processed += 1
    return str(soup)


def _register_stylesheet_link(item: epub.EpubHtml) -> None:
    """Register the annotation stylesheet on an EPUB HTML item.

    ebooklib rebuilds each document's ``<head>`` from its own template on
    write, so any ``<link>`` tag embedded in the serialized content string is
    discarded. The item-level ``add_link`` hook is the supported way to inject
    a stylesheet reference that survives that rebuild. Idempotent: a link
    pointing at the shared filename is added at most once per item.
    """
    # Compute path relative to this item's location within the epub.
    # Items in subdirectories (e.g. "text/part0001.html") need "../ell-annotations.css"
    # rather than "ell-annotations.css", which would resolve to the wrong location.
    item_dir = PurePosixPath(item.file_name).parent
    levels_up = len(item_dir.parts) if str(item_dir) != "." else 0
    href = "../" * levels_up + STYLESHEET_FILENAME
    if any(lnk.get("href") == href for lnk in item.links):
        return
    item.add_link(href=href, rel="stylesheet", type="text/css")


def _iter_text_nodes(node: BeautifulSoup | Tag | NavigableString) -> Iterator[NavigableString]:
    """Yield every :class:`~bs4.NavigableString` descendant of ``node``."""
    if isinstance(node, NavigableString):
        yield node
        return
    if isinstance(node, Tag):
        for child in list(node.children):
            yield from _iter_text_nodes(child)


def _parent_chain(node: NavigableString) -> set[str]:
    """Return the set of tag names along the ancestor chain of ``node``."""
    names: set[str] = set()
    current = node.parent
    while current is not None:
        name = getattr(current, "name", None)
        if name:
            names.add(name)
        current = current.parent
    return names


def _replace_with_html(text_node: NavigableString, html_fragment: str) -> None:
    """Replace ``text_node`` in-place with the children parsed from ``html_fragment``.

    The fragment is wrapped in a dummy ``<span>`` before parsing because the
    XML parser requires a single root element; its children are then hoisted
    into the original node's position.
    """
    wrapper = BeautifulSoup(f"<span>{html_fragment}</span>", "lxml-xml").find("span")
    if wrapper is None:
        return
    new_children = list(wrapper.children)
    parent = text_node.parent
    if parent is None:
        return
    index = parent.contents.index(text_node)
    text_node.extract()
    for offset, child in enumerate(new_children):
        parent.insert(index + offset, child)


STYLESHEET_FILENAME = "ell-annotations.css"
STYLESHEET_ITEM_ID = "ell-annotations-css"


def _add_stylesheet(book: epub.EpubBook, *, ruby_font_pct: float, active_level: str, annotation_grey_pct: float) -> None:
    """Attach the shared annotation stylesheet item to the EPUB.

    Args:
        book: The EPUB being assembled.
        ruby_font_pct: Ruby translation font-size as a percentage of the base
            word's font-size; threaded through to :func:`build_annotation_css`.
        active_level: CEFR level whose annotations are visible by default;
            baked into the stylesheet's rewrite-target block.
    """
    style = epub.EpubItem(
        uid=STYLESHEET_ITEM_ID,
        file_name=STYLESHEET_FILENAME,
        media_type="text/css",
        content=build_annotation_css(
            ruby_font_pct=ruby_font_pct,
            active_level=active_level,
            annotation_grey_pct=annotation_grey_pct,
        ).encode("utf-8"),
    )
    book.add_item(style)


class MissingStylesheetError(RuntimeError):
    """Raised when ``set-level`` cannot find the annotation stylesheet markers.

    The EPUB either wasn't produced by this tool or its CSS was rewritten by
    hand. Re-running :func:`annotate_epub` regenerates the marker block.
    """


def _find_stylesheet_item(book: epub.EpubBook) -> epub.EpubItem | None:
    """Return the bundled annotation stylesheet item, or ``None`` if missing."""
    for item in book.get_items():
        if item.file_name.endswith(STYLESHEET_FILENAME):
            return item
    return None


def set_visible_level(
    source: Path | str,
    destination: Path | str,
    level: str,
) -> None:
    """Rewrite the active-level CSS block of an annotated EPUB.

    The annotation stylesheet contains a marker-bracketed block that decides
    which CEFR levels are visible. Switching levels is therefore a CSS rewrite
    rather than a re-annotation: every word's ``ell-level-{lvl}`` class is
    already in place, the only change is which selectors are unhidden.

    Args:
        source: Path to a previously annotated EPUB.
        destination: Where to write the level-switched copy. Overwritten if it
            exists.
        level: CEFR level to make visible (case-insensitive).

    Raises:
        MissingStylesheetError: If ``source`` lacks the annotation stylesheet
            or its rewrite-target markers (e.g. produced by an older build).
    """
    book = epub.read_epub(str(source))
    style = _find_stylesheet_item(book)
    if style is None:
        msg = f"Annotation stylesheet {STYLESHEET_FILENAME!r} not found in {source!s}"
        raise MissingStylesheetError(msg)
    css = style.get_content().decode("utf-8")
    new_css = _rewrite_active_level_block(css, level)
    style.set_content(new_css.encode("utf-8"))
    # ebooklib drops item.links on read_epub, so the stylesheet link must be
    # re-registered on every document item before writing.
    for item in book.get_items_of_type(ITEM_DOCUMENT):
        _register_stylesheet_link(item)
    epub.write_epub(str(destination), book)


def _rewrite_active_level_block(css: str, level: str) -> str:
    """Replace the marker-bracketed block in ``css`` with one keyed by ``level``.

    Raises:
        MissingStylesheetError: When either marker line is missing.
    """
    begin_index = css.find(BEGIN_LEVEL_MARKER_PREFIX)
    end_index = css.find(END_LEVEL_MARKER)
    if begin_index == -1 or end_index == -1 or end_index <= begin_index:
        msg = "Annotation stylesheet is missing the active-level rewrite markers."
        raise MissingStylesheetError(msg)
    end_of_old_block = end_index + len(END_LEVEL_MARKER)
    return css[:begin_index] + build_active_level_block(level) + css[end_of_old_block:]


@dataclass
class StripStats:
    """Counters returned by :func:`strip_annotations`.

    Attributes:
        documents_processed: XHTML content documents visited.
        annotations_removed: Total ``ell-annot`` elements unwrapped.
    """

    documents_processed: int = 0
    annotations_removed: int = 0


def strip_annotations(
    source: Path | str,
    destination: Path | str,
) -> StripStats:
    """Remove every annotation from an EPUB, recovering the original prose.

    Walks each XHTML document and replaces every ``ruby.ell-annot`` /
    ``span.ell-annot`` with its base word, drops the bundled stylesheet
    item, and removes its ``<link>`` from each document.

    Args:
        source: Path to an annotated EPUB.
        destination: Where to write the stripped copy.

    Returns:
        Counters summarizing what was removed.
    """
    book = epub.read_epub(str(source))
    stats = StripStats()
    for item in list(book.get_items_of_type(ITEM_DOCUMENT)):
        original_html = item.get_content().decode("utf-8")
        new_html, removed = _strip_document(original_html)
        if removed:
            item.set_content(new_html.encode("utf-8"))
            stats.annotations_removed += removed
        _unregister_stylesheet_link(item)
        stats.documents_processed += 1

    style = _find_stylesheet_item(book)
    if style is not None:
        _remove_item(book, style)

    epub.write_epub(str(destination), book)
    return stats


def _strip_document(html: str) -> tuple[str, int]:
    """Remove every ell-annot element from ``html``; return ``(new_html, count)``.

    For ruby annotations the ``rt``/``rp`` children are dropped and the rest
    is unwrapped. For parenthetical annotations the ``span.ell-trans`` child
    is removed and the outer span unwrapped. The result is the bare base word
    in the same position as the original annotated form.

    BeautifulSoup's ``find_all(class_=...)`` shortcut is HTML-only — under
    the ``lxml-xml`` parser it never matches. We use the CSS selector form
    which works under both parsers.
    """
    soup = BeautifulSoup(html, "lxml-xml")
    removed = 0
    for tag in list(soup.select(".ell-annot")):
        if not isinstance(tag, Tag):
            continue
        for inner in list(tag.select("rt, rp, .ell-trans")):
            inner.decompose()
        tag.unwrap()
        removed += 1
    return str(soup), removed


def _unregister_stylesheet_link(item: epub.EpubHtml) -> None:
    """Remove every link to :data:`STYLESHEET_FILENAME` from ``item.links``."""
    item.links = [link for link in item.links if link.get("href") != STYLESHEET_FILENAME]


def _remove_item(book: epub.EpubBook, target: epub.EpubItem) -> None:
    """Remove ``target`` from the book and its spine, if present.

    ebooklib doesn't expose a public removal helper, so we mutate the
    underlying ``items`` list and ``spine`` directly. The spine cleanup is
    defensive — annotation stylesheets are not normally spine entries, but
    a future change could add them and we don't want to leave a dangling
    reference behind.
    """
    book.items = [item for item in book.items if item is not target]
    book.spine = [entry for entry in book.spine if not _spine_refers_to(entry, target)]


def _spine_refers_to(entry: object, target: epub.EpubItem) -> bool:
    """Return whether a ``book.spine`` entry points to ``target``."""
    ref = entry[0] if isinstance(entry, tuple) else entry
    return ref in (target.id, target.file_name)


def get_active_level(source: Path | str) -> str | None:
    """Return the visible CEFR level baked into ``source``'s stylesheet.

    Args:
        source: Path to an annotated EPUB.

    Returns:
        The uppercase CEFR level string parsed out of the BEGIN marker, or
        ``None`` when the stylesheet is missing or unrecognized.
    """
    book = epub.read_epub(str(source))
    style = _find_stylesheet_item(book)
    if style is None:
        return None
    css = style.get_content().decode("utf-8")
    begin = css.find(BEGIN_LEVEL_MARKER_PREFIX)
    if begin == -1:
        return None
    after_prefix = begin + len(BEGIN_LEVEL_MARKER_PREFIX)
    end = css.find(BEGIN_LEVEL_MARKER_SUFFIX, after_prefix)
    if end == -1:
        return None
    return css[after_prefix:end].strip().upper()
