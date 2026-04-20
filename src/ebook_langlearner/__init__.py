"""ebook-langlearner — annotate rare words in EPUB files with translations.

This package reads an EPUB, identifies rare words in the source language via a
frequency list (wordfreq) after lemmatization (simplemma), looks up translations
in one or more dictionary backends (Wiktionary/Kaikki, dict.cc), and writes a
new EPUB with inline annotations (``<ruby>`` or parenthetical) on every
occurrence of each rare word.

Example:
    >>> from ebook_langlearner.annotate import Annotator, AnnotationConfig
    >>> from ebook_langlearner.dictionaries import WiktionaryDictionary
    >>> from ebook_langlearner.epub_pipeline import annotate_epub
    >>> config = AnnotationConfig(source_lang="fr", target_lang="en", cutoff=3.0)
    >>> dictionary = WiktionaryDictionary("fr")
    >>> annotator = Annotator(dictionary, config)
    >>> annotate_epub("book.epub", "book.annotated.epub", annotator)
"""

__version__ = "0.1.0"
