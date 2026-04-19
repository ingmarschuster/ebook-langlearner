"""Composite dictionary that tries multiple backends in order."""

from __future__ import annotations

from .base import Dictionary, LookupKey


class CompositeDictionary(Dictionary):
    """Try each backend in order and return the first non-empty candidate list.

    Used to express preference ordering: e.g. a user-supplied dict.cc dictionary
    is consulted before the Wiktionary fallback. If the preferred source has no
    entry, the next backend is queried.
    """

    def __init__(self, backends: list[Dictionary]) -> None:
        """Initialize with a prioritized list of backends.

        Args:
            backends: Non-empty list of backends in preference order. Earlier
                entries win when they have any candidates.

        Raises:
            ValueError: If ``backends`` is empty.
        """
        if not backends:
            raise ValueError("CompositeDictionary requires at least one backend")
        self._backends = backends

    def candidates(self, key: LookupKey) -> list[str]:
        """Return candidates from the first backend that has any.

        Args:
            key: The lookup key.

        Returns:
            The first non-empty candidate list across backends, or an empty
            list if no backend has a match.
        """
        for backend in self._backends:
            result = backend.candidates(key)
            if result:
                return result
        return []
