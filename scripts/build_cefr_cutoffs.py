"""Precompute per-language CEFR → Zipf cutoff tables.

Maps each CEFR level to the Zipf frequency of the N-th most common lemma in
the language, where N is the CEFR receptive-vocabulary-size target for that
level. A "B1 reader" is assumed to know the top-2500 lemmas of their target
language, so the B1 annotation cutoff is the aggregated Zipf of rank 2500.

Why per-language: morphologically rich languages (de, pl, ru) spread surface
frequency across many inflected forms, so the *surface* Zipf of the N-th
ranked lemma differs substantially from a fusional/analytic language (en, fr,
sv). Using lemma-aggregated Zipf (see :mod:`build_lemma_frequencies`) is what
makes the per-language mapping meaningful: we rank by the same unit the
annotator checks against.

The CEFR vocabulary-size targets below are the widely-cited receptive ranges
from Milton (2013) and related CEFR-alignment studies; individual published
wordlists (Goethe A1, Niveau A1, English Vocabulary Profile, etc.) cluster
around these sizes. Using a size-based calibration on each language's own
lemma distribution is a principled approximation to running against those
lists, and it avoids shipping copyrighted wordlists.

Output: ``src/ebook_langlearner/data/cefr_cutoffs.json`` as
``{lang: {level: zipf}}``. Committed to the repo; regenerate after updating
the lemma-frequency tables.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

from ebook_langlearner.languages import CORE_LANGUAGES
from ebook_langlearner.lemma_frequency import _load_table

CEFR_VOCAB_SIZES: dict[str, int] = {
    "A1": 750,
    "A2": 1500,
    "B1": 2500,
    "B2": 4500,
    "C1": 8000,
    "C2": 16000,
}
"""CEFR receptive-vocabulary targets (lemma counts per level).

Values are mid-range consensus figures from Milton (2013) "Measuring the
contribution of vocabulary knowledge to proficiency in the four skills" and
the CEFR Companion Volume vocabulary descriptors. Published per-language
lists (Goethe-Institut, Instituto Cervantes, Cambridge EVP, Referentiel
Niveau A1) cluster around these sizes.
"""

DATA_DIR = Path(__file__).resolve().parent.parent / "src" / "ebook_langlearner" / "data"
OUT_PATH = DATA_DIR / "cefr_cutoffs.json"


def cutoffs_for_language(lang: str) -> dict[str, float]:
    """Compute CEFR → Zipf cutoffs for ``lang`` from its lemma-frequency table.

    Ranks all known lemmas by aggregated Zipf (descending); the Zipf value at
    rank ``N = CEFR_VOCAB_SIZES[level]`` becomes the cutoff for that level.
    Words strictly below this Zipf are "not in the top-N" and thus candidates
    for annotation at that level.
    """
    table = _load_table(lang)
    if not table:
        msg = f"No lemma-frequency table for {lang!r}; run build_lemma_frequencies first."
        raise RuntimeError(msg)
    ranked = sorted(table.values(), reverse=True)
    cutoffs: dict[str, float] = {}
    for level, size in CEFR_VOCAB_SIZES.items():
        if size <= len(ranked):
            cutoffs[level] = round(ranked[size - 1], 3)
        else:
            cutoffs[level] = round(ranked[-1], 3)
    return cutoffs


def main() -> int:
    """Build CEFR cutoff tables for every language in :data:`CORE_LANGUAGES`."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    result: dict[str, dict[str, float]] = {}
    for lang in CORE_LANGUAGES:
        cutoffs = cutoffs_for_language(lang)
        result[lang] = cutoffs
        summary = "  ".join(f"{lvl}={z:.2f}" for lvl, z in cutoffs.items())
        print(f"{lang}: {summary}")
    OUT_PATH.write_text(
        json.dumps(result, indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"\nWrote {OUT_PATH.relative_to(Path.cwd())}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
