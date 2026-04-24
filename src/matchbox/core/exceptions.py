"""Matchbox-specific exceptions."""

from __future__ import annotations


class MatchboxError(Exception):
    """Base class for all Matchbox errors."""


class ProfileNotFoundError(MatchboxError):
    """Raised when a people/{name}/ directory or required file is missing."""


class SchemaVersionError(MatchboxError):
    """Raised when a profile's schema_version is unknown or unsupported."""


class InvalidStateError(MatchboxError):
    """Raised when a job state transition is invalid."""


class ExclusionError(MatchboxError):
    """Raised when a job is blocked by a hard exclusion rule."""


class BudgetExceededError(MatchboxError):
    """Raised when a tailor batch would exceed the declared cost budget."""


class GateFailureError(MatchboxError):
    """Raised when a quality gate rejects generated content."""

    def __init__(self, gate: str, reason: str) -> None:
        self.gate = gate
        self.reason = reason
        super().__init__(f"Gate '{gate}' failed: {reason}")
