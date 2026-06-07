"""BYOK AI layer: voice-check, provider config, the secret key, and the
localhost streaming proxy.

The app holds no LLM client. The proxy forwards the user's prompt to the user's
provider with the user's key and terminates SSE locally -- the key never leaves
the device and is never returned to the browser. `/api/voice-check` guards FORM
ONLY (banned words/openers, em-dashes, contractions, word count); it does not
verify factual grounding, and a fabricated metric passes it clean. Factual
safety comes from feeding only verified facts (`/api/library/facts`), the §13
never-invent prompt, and the user always reading and sending -- not this gate.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator, Callable
from typing import Any

import httpx
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from matchbox.core import secrets
from matchbox.core.settings import get_setting, set_setting
from matchbox.polish import load_voice_rules, validate_voice
from matchbox.web.deps import ConnDep, ProfileDep

router = APIRouter(prefix="/api")

VALID_SCOPES = {"cv_bullet", "cover", "answer"}
VALID_PROVIDERS = {"anthropic", "openai"}
# Default models -- user-overridable via POST /api/ai/config. The proxy calls
# the user's provider with the user's key; these are only the starting points.
_DEFAULT_MODEL = {"anthropic": "claude-opus-4-8", "openai": "gpt-4o"}


# ── voice-check (form only) ─────────────────────────────────────────────────────


class VoiceCheckBody(BaseModel):
    text: str
    scope: str = "cover"


@router.post("/voice-check")
def voice_check(body: VoiceCheckBody) -> dict[str, Any]:
    """Form/voice consistency only -- NOT a fact check (see module docstring)."""
    scope = body.scope if body.scope in VALID_SCOPES else "cover"
    violations = validate_voice(body.text, load_voice_rules(), scope=scope)
    return {
        "ok": not violations,
        "scope": scope,
        "violations": [{"rule": v.rule, "detail": v.detail} for v in violations],
    }


# ── provider config (non-secret) + key (write-only) ─────────────────────────────


class AIConfigBody(BaseModel):
    provider: str | None = None
    on: bool | None = None
    model: str | None = None


class AIKeyBody(BaseModel):
    key: str


def _provider(conn: Any) -> str:
    p = get_setting(conn, "ai_provider", "anthropic") or "anthropic"
    return p if p in VALID_PROVIDERS else "anthropic"


def _model(conn: Any, provider: str) -> str:
    return (
        get_setting(conn, f"ai_model_{provider}", _DEFAULT_MODEL[provider])
        or _DEFAULT_MODEL[provider]
    )


def _ai_on(conn: Any) -> bool:
    return (get_setting(conn, "ai_on", "true") or "true") != "false"


def _config_dict(conn: Any, profile: str) -> dict[str, Any]:
    provider = _provider(conn)
    return {
        "provider": provider,
        "model": _model(conn, provider),
        "on": _ai_on(conn),
        "hasKey": secrets.has_key(profile),  # boolean only -- never the key itself
    }


@router.get("/ai/config")
def ai_config(conn: ConnDep, profile: ProfileDep) -> dict[str, Any]:
    return _config_dict(conn, profile)


@router.post("/ai/config")
def set_ai_config(body: AIConfigBody, conn: ConnDep, profile: ProfileDep) -> dict[str, Any]:
    if body.provider is not None:
        if body.provider not in VALID_PROVIDERS:
            raise HTTPException(status_code=400, detail=f"unknown provider: {body.provider!r}")
        set_setting(conn, "ai_provider", body.provider)
    if body.on is not None:
        set_setting(conn, "ai_on", "true" if body.on else "false")
    if body.model is not None and body.model.strip():
        set_setting(conn, f"ai_model_{_provider(conn)}", body.model.strip())
    return _config_dict(conn, profile)


@router.post("/ai/key")
def set_ai_key(body: AIKeyBody, conn: ConnDep, profile: ProfileDep) -> dict[str, Any]:
    """Persist the provider key to the 0600 secret file for this profile."""
    secrets.write_key(body.key, profile)
    return _config_dict(conn, profile)


@router.delete("/ai/key")
def clear_ai_key(conn: ConnDep, profile: ProfileDep) -> dict[str, Any]:
    secrets.clear_key(profile)
    return _config_dict(conn, profile)


# ── streaming proxy ─────────────────────────────────────────────────────────────


class StreamBody(BaseModel):
    prompt: str
    system: str | None = None
    max_tokens: int = 1024


def _sse(obj: dict[str, Any]) -> bytes:
    return f"data: {json.dumps(obj)}\n\n".encode()


def _anthropic_delta(obj: dict[str, Any]) -> str:
    if obj.get("type") == "content_block_delta":
        delta = obj.get("delta") or {}
        if delta.get("type") == "text_delta":
            return str(delta.get("text") or "")
    return ""


def _openai_delta(obj: dict[str, Any]) -> str:
    choices = obj.get("choices") or []
    if choices:
        return str((choices[0].get("delta") or {}).get("content") or "")
    return ""


def _request_for(
    provider: str, model: str, key: str, system: str, prompt: str, max_tokens: int
) -> tuple[str, dict[str, str], dict[str, Any], Callable[[dict[str, Any]], str]]:
    if provider == "anthropic":
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_tokens,
            "stream": True,
            "messages": [{"role": "user", "content": prompt}],
        }
        if system:
            payload["system"] = system
        headers = {
            "x-api-key": key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        return "https://api.anthropic.com/v1/messages", headers, payload, _anthropic_delta
    messages = ([{"role": "system", "content": system}] if system else []) + [
        {"role": "user", "content": prompt}
    ]
    payload = {"model": model, "stream": True, "messages": messages, "max_tokens": max_tokens}
    headers = {"authorization": f"Bearer {key}", "content-type": "application/json"}
    return "https://api.openai.com/v1/chat/completions", headers, payload, _openai_delta


async def _relay(
    provider: str, model: str, key: str, system: str, prompt: str, max_tokens: int
) -> AsyncIterator[bytes]:
    """Forward to the provider, re-emit normalized `data: {"text": ...}` SSE.

    Errors are surfaced as a single `{"error": ...}` frame so the browser can
    fall back to its demo stream; the key is never echoed."""
    url, headers, payload, pick = _request_for(provider, model, key, system, prompt, max_tokens)
    try:
        async with (
            httpx.AsyncClient(timeout=httpx.Timeout(60.0, read=120.0)) as client,
            client.stream("POST", url, headers=headers, json=payload) as resp,
        ):
            if resp.status_code >= 400:
                body = (await resp.aread()).decode("utf-8", "replace")[:500]
                yield _sse({"error": f"{provider} {resp.status_code}", "detail": body})
                yield b"data: [DONE]\n\n"
                return
            async for line in resp.aiter_lines():
                line = line.strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                try:
                    piece = pick(json.loads(data))
                except (json.JSONDecodeError, KeyError, IndexError, TypeError):
                    continue
                if piece:
                    yield _sse({"text": piece})
    except httpx.HTTPError as e:
        yield _sse({"error": "proxy_error", "detail": str(e)})
    yield b"data: [DONE]\n\n"


@router.post("/ai/stream")
def ai_stream(body: StreamBody, conn: ConnDep, profile: ProfileDep) -> StreamingResponse:
    """Localhost SSE proxy to the user's provider. 409 when no key / disabled
    so the browser streams its demo fallback (the real artifact still comes from
    the manual handoff).

    Sync endpoint on purpose: it runs in the threadpool where the per-request
    sqlite connection lives, resolves the provider/model/key into plain values,
    then hands the async relay (which never touches the DB) to StreamingResponse."""
    key = secrets.read_key(profile)
    if not _ai_on(conn) or not key:
        raise HTTPException(status_code=409, detail="no provider key configured")
    provider = _provider(conn)
    model = _model(conn, provider)
    return StreamingResponse(
        _relay(provider, model, key, body.system or "", body.prompt, body.max_tokens),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
