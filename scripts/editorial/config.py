"""Posting Auto 2.0 editorial: quality config, review, revise, decide."""

from __future__ import annotations

import os


def _env(name: str, default: str = "") -> str:
    return os.getenv(name, default).strip()


def _env_int(name: str, default: int) -> int:
    raw = _env(name)
    if not raw:
        return default
    try:
        value = int(raw)
    except ValueError:
        return default
    return value if value >= 0 else default


def max_revision_count() -> int:
    return _env_int("QUALITY_MAX_REVISION_COUNT", 2)


def minimum_story_count() -> int:
    return _env_int("QUALITY_MINIMUM_STORY_COUNT", 3)


def auto_publish_enabled() -> bool:
    return _env("AUTO_PUBLISH", "0").lower() in {"1", "true", "yes"}


def human_gates_enabled() -> bool:
    """Normal draft gates. Disabled for autonomous editorial path."""
    if _env("HUMAN_GATES", "").lower() in {"0", "false", "no"}:
        return False
    if _env("MVP_MODE", "").lower() == "autonomous":
        return False
    return True


def ollama_model() -> str:
    return _env("OLLAMA_MODEL", "qwen2.5:7b") or "qwen2.5:7b"


def ollama_host() -> str:
    return _env("OLLAMA_HOST_URL", "http://127.0.0.1:11434") or "http://127.0.0.1:11434"
