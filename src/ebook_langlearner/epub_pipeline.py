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
from typing import TYPE_CHECKING

from bs4 import BeautifulSoup, NavigableString, Tag
from ebooklib import ITEM_DOCUMENT, epub

from .render import RUBY_CSS

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

    _add_stylesheet(book)
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
    for existing in item.links:
        if existing.get("href") == STYLESHEET_FILENAME:
            return
    item.add_link(href=STYLESHEET_FILENAME, rel="stylesheet", type="text/css")


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


def _add_stylesheet(book: epub.EpubBook) -> None:
    """Attach the shared annotation stylesheet item to the EPUB."""
    style = epub.EpubItem(
        uid=STYLESHEET_ITEM_ID,
        file_name=STYLESHEET_FILENAME,
        media_type="text/css",
        content=RUBY_CSS.encode("utf-8"),
    )
    book.add_item(style)
