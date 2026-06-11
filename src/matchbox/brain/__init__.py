"""In-app reasoning runner (the "brain") driven by the user's own BYOK key.

This package lets a first-time user run ingest and tailoring entirely inside the
app, using the provider key they stored for the BYOK proxy -- no second terminal,
no Claude Code. It is the *convenience* path, not a replacement: Claude Code
remains the documented, fully-supported no-key fallback (see CLAUDE.md /
AGENTS.md), and the brain encodes the exact same rules those instructions give.

The no-fabrication guarantee does NOT live here. This package only proposes:
it asks the configured model for ingest/requirements/selection/polish JSON,
validates the JSON against the generated schemas, and hands it to the same
deterministic core CLIs the manual path uses (`ingest`, `save_requirements`,
`assemble_one`, `polish_run`). The core validates every selected id is a real
verified bullet/project/skill and voice-gates the summary/headline; a model that
hallucinates an id or a banned word is rejected there, exactly as Claude Code's
output would be. The brain is plain Python: no FastAPI imports here.
"""

from __future__ import annotations

from matchbox.brain.llm import BrainError, Completer, byok_completer

__all__ = ["BrainError", "Completer", "byok_completer"]
