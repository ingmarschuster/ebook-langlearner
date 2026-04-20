"""Supported source and target languages.

Defines the core European language set the project supports and a single
validation helper used throughout the CLI and annotator.
"""

from __future__ import annotations

CORE_LANGUAGES: dict[str, str] = {
    "en": "English",
    "de": "German",
    "fr": "French",
    "es": "Spanish",
    "it": "Italian",
    "nl": "Dutch",
    "pt": "Portuguese",
    "pl": "Polish",
    "sv": "Swedish",
}
"""Mapping of ISO 639-1 codes to human-readable names for supported languages."""


class UnsupportedLanguageError(ValueError):
    """Raised when a language code is outside :data:`CORE_LANGUAGES`."""


def require_supported(code: str) -> str:
    """Validate and normalize a language code.

    Args:
        code: A language code, case-insensitive. Expected to be a two-letter
            ISO 639-1 code such as ``"fr"`` or ``"DE"``.

    Returns:
        The lowercased language code.

    Raises:
        UnsupportedLanguageError: If ``code`` is not in :data:`CORE_LANGUAGES`.
    """
    code = code.lower()
    if code not in CORE_LANGUAGES:
        supported = ", ".join(sorted(CORE_LANGUAGES))
        raise UnsupportedLanguageError(f"Language {code!r} is not in the core set ({supported}).")
    return code
