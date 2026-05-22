"""Person loader — reads people/{name}/* into a Person object.

Usage:
    from matchbox.core.person import load_person
    person = load_person("shiva")
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from matchbox.core.exceptions import ProfileNotFoundError
from matchbox.core.migrations import migrate_profile
from matchbox.core.schema import Person, Profile, VoiceRules

log = logging.getLogger(__name__)

_yaml = YAML()
_yaml.preserve_quotes = True


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[3]  # src/matchbox/core/person.py → repo root


def _load_yaml(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as fh:
        data = _yaml.load(fh)
    return dict(data) if data else {}


def _people_dir(name: str) -> Path:
    return _repo_root() / "people" / name


def _shared_dir() -> Path:
    return _repo_root() / "shared"


def load_person(name: str) -> Person:
    """
    Load and validate a Person from people/{name}/.

    Raises ProfileNotFoundError if the directory or profile.yaml is missing.
    """
    profile_dir = _people_dir(name)
    if not profile_dir.exists():
        raise ProfileNotFoundError(f"Profile directory not found: {profile_dir}")

    profile_path = profile_dir / "profile.yaml"
    if not profile_path.exists():
        raise ProfileNotFoundError(f"profile.yaml not found in: {profile_dir}")

    # Load and migrate profile
    raw_profile = _load_yaml(profile_path)
    raw_profile = migrate_profile(raw_profile)
    profile = Profile.model_validate(raw_profile)

    # Load voice rules: shared defaults + per-person overrides
    voice = _load_voice_rules(name)

    # Load stories
    stories_path = profile_dir / "stories.md"
    stories_text = stories_path.read_text(encoding="utf-8") if stories_path.exists() else ""
    if not stories_text:
        log.warning("No stories.md found for profile '%s'", name)

    return Person(name=name, profile=profile, voice=voice, stories_text=stories_text)


def _load_voice_rules(name: str) -> VoiceRules:
    shared_path = _shared_dir() / "voice-rules.yaml"
    defaults: dict[str, Any] = _load_yaml(shared_path) if shared_path.exists() else {}

    override_path = _people_dir(name) / "voice.yaml"
    if not override_path.exists():
        return VoiceRules.merge(defaults, {})

    overrides = _load_yaml(override_path)
    return VoiceRules.merge(defaults, overrides)
