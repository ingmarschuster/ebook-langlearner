"""Tests for the text-level annotator."""

from __future__ import annotations

from ebook_langlearner.annotate import AnnotationConfig, Annotator
from ebook_langlearner.render import DEFAULT_RUBY_FONT_PCT, AnnotationFormat


def _annotator(static_dict_factory, *, fmt=AnnotationFormat.RUBY, cutoff=4.5):
    dictionary = static_dict_factory(
        "fr",
        {
            ("aubépine", "en"): ["hawthorn"],
            ("crépuscule", "en"): ["twilight", "dusk"],
        },
    )
    cfg = AnnotationConfig(
        source_lang="fr",
        target_lang="en",
        cutoff=cutoff,
        fmt=fmt,
    )
    return Annotator(dictionary, cfg)


def test_rare_word_is_wrapped_in_ruby(static_dict_factory):
    ann = _annotator(static_dict_factory)
    out = ann.annotate_text("L'aubépine fleurit.")
    assert "<ruby" in out
    assert "aubépine" in out
    assert "hawthorn" in out


def test_common_word_is_not_annotated(static_dict_factory):
    ann = _annotator(static_dict_factory)
    # "et" (Fr. "and") is extremely common; must not be wrapped.
    out = ann.annotate_text("Le chat et le chien.")
    assert "<ruby" not in out


def test_top_two_translations_rendered_joined(static_dict_factory):
    ann = _annotator(static_dict_factory)
    out = ann.annotate_text("Le crépuscule.")
    assert "twilight/dusk" in out


def test_parenthetical_format_uses_brackets(static_dict_factory):
    ann = _annotator(static_dict_factory, fmt=AnnotationFormat.PARENTHETICAL)
    out = ann.annotate_text("L'aubépine.")
    assert "[hawthorn]" in out
    assert "<ruby" not in out


def test_proper_noun_mid_sentence_is_skipped(static_dict_factory):
    ann = _annotator(static_dict_factory)
    out = ann.annotate_text("Un ami à Paris.")
    # Paris is capitalized mid-sentence: no ruby wrap even if we had a translation.
    assert "<ruby" not in out


def test_numeric_tokens_are_skipped(static_dict_factory):
    ann = _annotator(static_dict_factory)
    out = ann.annotate_text("L'an 2024.")
    assert "2024" in out
    assert "<ruby" not in out.split("2024")[0]


def test_short_words_are_skipped(static_dict_factory):
    ann = _annotator(static_dict_factory)
    out = ann.annotate_text("L'a")
    # Nothing annotated because "a" is a single letter.
    assert "<ruby" not in out


def test_punctuation_and_whitespace_preserved(static_dict_factory):
    ann = _annotator(static_dict_factory)
    text = "— L'aubépine,    vraiment?"
    out = ann.annotate_text(text)
    assert out.startswith("— ")
    assert ",    " in out
    assert out.endswith("?")


def test_every_occurrence_annotated(static_dict_factory):
    ann = _annotator(static_dict_factory)
    out = ann.annotate_text("aubépine et aubépine")
    assert out.count("<ruby") == 2


def test_html_special_chars_escaped(static_dict_factory):
    ann = _annotator(static_dict_factory)
    out = ann.annotate_text("a < b & c")
    assert "&lt;" in out
    assert "&amp;" in out


def test_common_surface_form_not_annotated_even_if_lemma_is_rare(static_dict_factory):
    """Guard against lemmatizer false positives on common verb forms.

    simplemma sometimes collapses a very common inflected form (e.g. French
    ``étais`` = "I was", Zipf ~5.4) to a rare noun homograph (``étai`` =
    strut, Zipf ~2.7). Without a surface-form frequency gate the pipeline
    would happily wrap every "j'étais" with "Stützbalken", which is
    actively misleading for a learner.
    """
    # Provide a translation for the noun lemma "étai" so only the surface-form
    # gate can prevent the annotation.
    dictionary = static_dict_factory("fr", {("étai", "en"): ["strut"]})
    cfg = AnnotationConfig(source_lang="fr", target_lang="en", cutoff=3.0)
    ann = Annotator(dictionary, cfg)
    out = ann.annotate_text("j'étais fatigué")
    assert "<ruby" not in out, f"common 'étais' must not be annotated, got: {out!r}"


def test_no_dictionary_hit_leaves_word_plain(static_dict_factory):
    # The dictionary knows "aubépine" but not "pétunia".
    ann = _annotator(static_dict_factory)
    out = ann.annotate_text("Le pétunia est rare.")
    # wordfreq may treat pétunia as rare, but without a candidate we don't wrap.
    assert "pétunia" in out
    assert "<ruby" not in out or "pétunia" not in _inside_ruby(out)


def test_annotation_config_defaults_ruby_font_pct():
    cfg = AnnotationConfig(source_lang="fr", target_lang="en", cutoff=3.0)
    assert cfg.ruby_font_pct == DEFAULT_RUBY_FONT_PCT


def test_annotator_exposes_config_via_property(static_dict_factory):
    dictionary = static_dict_factory("fr", {})
    cfg = AnnotationConfig(source_lang="fr", target_lang="en", cutoff=3.0, ruby_font_pct=72.5)
    annotator = Annotator(dictionary, cfg)
    assert annotator.config is cfg
    assert annotator.config.ruby_font_pct == 72.5


def _inside_ruby(html: str) -> str:
    """Return the concatenation of all text inside <ruby> tags."""
    inside = []
    cursor = 0
    while True:
        start = html.find("<ruby", cursor)
        if start == -1:
            break
        end = html.find("</ruby>", start)
        if end == -1:
            break
        inside.append(html[start:end])
        cursor = end + len("</ruby>")
    return "".join(inside)
