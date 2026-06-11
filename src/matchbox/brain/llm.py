"""The BYOK completer: a non-streaming, synchronous call to the user's provider.

`Completer` is a tiny protocol -- `(system, user) -> str` -- so the runner never
touches httpx or the secret store directly and tests can inject a fake callable.
`byok_completer` builds a real one from the stored key plus the provider/model the
user configured for the streaming proxy (`ai.py`), hitting the same hosts and
request shapes as that proxy but with `stream: false` (the runner needs the whole
JSON document, not token deltas).

When no key is configured, building the completer raises ``BrainError("no key")``
so callers can return the BYOK-specific 409 and the UI can fall back to the
documented Claude Code path.
"""

from __future__ import annotations

import sqlite3
from typing import Any, Protocol

import httpx

from matchbox.core import secrets
from matchbox.core.settings import get_setting

# Mirror ai.py's provider vocabulary, default model map, and hosts so the brain
# and the streaming proxy stay in lockstep (one source of truth would be nicer,
# but ai.py keeps these private; duplicating the two constants is cheaper than a
# new shared module and is covered by the tests below).
VALID_PROVIDERS = {"anthropic", "openai"}
_DEFAULT_MODEL = {"anthropic": "claude-opus-4-8", "openai": "gpt-4o"}
_ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
_OPENAI_URL = "https://api.openai.com/v1/chat/completions"

# The brain asks for a whole JSON document; give it room and a generous read
# timeout (extraction/selection over a long JD is slow but not interactive).
_MAX_TOKENS = 4096
_TIMEOUT = httpx.Timeout(30.0, read=120.0)


class BrainError(Exception):
    """A brain run could not proceed.

    Carries a human-readable message (no key, model returned non-JSON, schema
    validation failed after a retry, job missing, ...). The web layer maps these
    onto 409/404/422 as appropriate; the runner raises them loudly rather than
    papering over a failure.
    """


class Completer(Protocol):
    """A synchronous text completion: ``(system, user) -> assistant text``.

    Deliberately minimal so the runner depends on nothing provider-specific and
    tests inject a plain callable. Implementations should return the model's raw
    text response (the runner strips code fences and parses JSON itself)."""

    def __call__(self, system: str, user: str) -> str: ...


def _provider(conn: sqlite3.Connection) -> str:
    p = get_setting(conn, "ai_provider", "anthropic") or "anthropic"
    return p if p in VALID_PROVIDERS else "anthropic"


def _model(conn: sqlite3.Connection, provider: str) -> str:
    return (
        get_setting(conn, f"ai_model_{provider}", _DEFAULT_MODEL[provider])
        or _DEFAULT_MODEL[provider]
    )


def _anthropic_text(data: dict[str, Any]) -> str:
    """Concatenate the text blocks of a non-streaming Anthropic message."""
    parts = []
    for block in data.get("content") or []:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(str(block.get("text") or ""))
    return "".join(parts)


def _openai_text(data: dict[str, Any]) -> str:
    choices = data.get("choices") or []
    if not choices:
        return ""
    message = choices[0].get("message") or {}
    return str(message.get("content") or "")


def _complete(provider: str, model: str, key: str, system: str, user: str) -> str:
    """One blocking, non-streaming completion against the user's provider.

    Same hosts/headers as ai.py's proxy, but ``stream`` is omitted (we want the
    full document). Network/HTTP failures become a ``BrainError`` so the runner's
    loud-failure contract holds end to end; the key is never echoed in the error.
    """
    if provider == "anthropic":
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": _MAX_TOKENS,
            "messages": [{"role": "user", "content": user}],
        }
        if system:
            payload["system"] = system
        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        url, pick = _ANTHROPIC_URL, _anthropic_text
    else:
        messages = ([{"role": "system", "content": system}] if system else []) + [
            {"role": "user", "content": user}
        ]
        payload = {"model": model, "messages": messages, "max_tokens": _MAX_TOKENS}
        headers = {"authorization": f"Bearer {key}", "content-type": "application/json"}
        url, pick = _OPENAI_URL, _openai_text

    try:
        with httpx.Client(timeout=_TIMEOUT) as client:
            resp = client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as e:
        raise BrainError(f"{provider} request failed: {e}") from e
    if resp.status_code >= 400:
        body = resp.text[:500]
        raise BrainError(f"{provider} {resp.status_code}: {body}")
    try:
        data = resp.json()
    except ValueError as e:
        raise BrainError(f"{provider} returned non-JSON response") from e
    text = pick(data)
    if not text.strip():
        raise BrainError(f"{provider} returned an empty completion")
    return text


def byok_completer(conn: sqlite3.Connection, profile: str) -> Completer:
    """Build a `Completer` from the stored key + configured provider/model.

    Resolves the key and the provider/model up front (the same per-request
    sqlite connection ai_stream uses), so the returned callable closes over
    plain strings and never touches the DB or the secret store again -- safe to
    call from a worker thread. Raises ``BrainError`` when no key is configured.
    """
    key = secrets.read_key(profile)
    if not key:
        raise BrainError("no key")
    provider = _provider(conn)
    model = _model(conn, provider)

    def complete(system: str, user: str) -> str:
        return _complete(provider, model, key, system, user)

    return complete
