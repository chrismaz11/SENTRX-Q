"""Configuration loader for SENTRX-Q.

Reads ``config/default.yml``, expands ``${ENV_VAR}`` placeholders from the
process environment (or a ``.env`` file), and exposes the result as a plain
nested dictionary.
"""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import Any

import yaml

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:
    pass  # python-dotenv is optional during testing

_ENV_RE = re.compile(r"\$\{([^}:]+)(?::-(.*?))?\}")

_DEFAULT_CONFIG_PATH = Path(__file__).parent / "config" / "default.yml"


def _expand_env(value: str) -> str:
    """Replace ``${VAR}`` / ``${VAR:-default}`` placeholders with env values."""

    def _replace(match: re.Match) -> str:  # type: ignore[type-arg]
        var, default = match.group(1), match.group(2)
        return os.environ.get(var, default or "")

    return _ENV_RE.sub(_replace, value)


def _walk(obj: Any) -> Any:
    """Recursively expand environment variables in a parsed YAML structure."""
    if isinstance(obj, dict):
        return {k: _walk(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_walk(item) for item in obj]
    if isinstance(obj, str):
        return _expand_env(obj)
    return obj


def load_config(path: str | Path | None = None) -> dict[str, Any]:
    """Load and return the SENTRX-Q configuration dictionary.

    Parameters
    ----------
    path:
        Path to the YAML config file.  Defaults to ``config/default.yml``
        relative to the project root.
    """
    config_path = Path(path) if path else _DEFAULT_CONFIG_PATH
    with config_path.open("r", encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return _walk(raw)
