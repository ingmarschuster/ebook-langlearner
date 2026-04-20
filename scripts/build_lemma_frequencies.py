"""Precompute lemma-aggregated Zipf frequencies and write them to package data.

For each supported language, iterate :func:`wordfreq.get_frequency_dict`
(surface-form frequencies) and fold them onto their :mod:`simplemma` lemma,
summing decimal frequencies. The result is written as gzipped JSON under
``src/ebook_langlearner/data/lemma_freq_{lang}.json.gz`` as a mapping
``{lemma: zipf}`` with Zipf values rounded to 3 decimals.

Why precompute: iterating and lemmatizing ~300 k surface forms per language
takes about a second, but running that at every import would make the CLI
sluggish and add a simplemma dependency at import time. Shipping the
aggregates as data keeps the pipeline startup-free and makes the computation
reproducible across installs.

Run via ``uv run python scripts/build_lemma_frequencies.py``. The resulting
files are committed to the repo.
"""

from __future__ import annotations

import gzip
import json
import sys
from pathlib import Path

import simplemma
from wordfreq import freq_to_zipf, get_frequency_dict

from ebook_langlearner.languages import CORE_LANGUAGES

MIN_LEMMA_ZIPF = 1.5
"""Prune lemmas whose aggregated Zipf is below this threshold.

The annotator never uses cutoffs below about 2.5 in practice, so any lemma
with Zipf < 1.5 is unconditionally "rare" from its perspective; storing them
would only inflate the shipped data files. Missing keys are interpreted as
Zipf 0.0 by the loader (see :mod:`ebook_langlearner.lemma_frequency`).
"""

DATA_DIR = Path(__file__).resolve().parent.parent / "src" / "ebook_langlearner" / "data"


def build_for_language(lang: str) -> tuple[int, int]:
    """Build one language's lemma-frequency file, returning ``(surfaces, lemmas)``."""
    surfaces = get_frequency_dict(lang, wordlist="best")
    aggregated: dict[str, float] = {}
    for surface, freq in surfaces.items():
        try:
            lemma = simplemma.lemmatize(surface, lang=lang)
        except (ValueError, LookupError):
            lemma = surface
        aggregated[lemma] = aggregated.get(lemma, 0.0) + freq
    min_freq = 10 ** (MIN_LEMMA_ZIPF - 9)
    pruned = {
        lemma: round(freq_to_zipf(total), 3)
        for lemma, total in aggregated.items()
        if total >= min_freq
    }
    payload = json.dumps(pruned, separators=(",", ":"), ensure_ascii=False)
    out_path = DATA_DIR / f"lemma_freq_{lang}.json.gz"
    out_path.write_bytes(gzip.compress(payload.encode("utf-8"), compresslevel=9))
    return len(surfaces), len(pruned)


def main() -> int:
    """Build lemma-frequency files for every language in :data:`CORE_LANGUAGES`."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    for lang in CORE_LANGUAGES:
        n_surface, n_lemma = build_for_language(lang)
        size_kb = (DATA_DIR / f"lemma_freq_{lang}.json.gz").stat().st_size // 1024
        print(f"{lang}: surfaces={n_surface:>6}  lemmas_kept={n_lemma:>6}  size={size_kb:>5}KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
