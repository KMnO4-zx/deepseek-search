"""API key persistence — read/write to XDG config directory."""

from __future__ import annotations

import json
import os
from pathlib import Path


def _config_dir() -> Path:
    """Return the config directory (XDG-compatible)."""
    xdg = os.environ.get("XDG_CONFIG_HOME")
    if xdg:
        base = Path(xdg)
    else:
        base = Path.home() / ".config"
    return base / "deepseek-search"


def _config_file() -> Path:
    return _config_dir() / "config.json"


def save_api_key(api_key: str) -> Path:
    """Persist the API key to the config file. Returns the file path."""
    cfg_dir = _config_dir()
    cfg_dir.mkdir(parents=True, exist_ok=True)
    cfg_file = _config_file()
    cfg_file.write_text(json.dumps({"api_key": api_key}, indent=2) + "\n")
    cfg_file.chmod(0o600)  # user read/write only
    return cfg_file


def load_api_key() -> str | None:
    """Load the API key from the config file, or None."""
    cfg_file = _config_file()
    if not cfg_file.exists():
        return None
    try:
        data = json.loads(cfg_file.read_text())
        return data.get("api_key") or None
    except (json.JSONDecodeError, OSError):
        return None


def clear_api_key() -> bool:
    """Remove the config file. Returns True if it existed."""
    cfg_file = _config_file()
    if cfg_file.exists():
        cfg_file.unlink()
        return True
    return False


def resolve_api_key(cli_key: str | None = None) -> str:
    """
    Resolve API key with priority:
    1. CLI argument
    2. DEEPSEEK_API_KEY environment variable
    3. Config file (~/.config/deepseek-search/config.json)
    """
    key = cli_key or os.environ.get("DEEPSEEK_API_KEY") or load_api_key()
    if not key:
        raise ValueError(
            "DEEPSEEK_API_KEY is required.\n\n"
            "  Set it once:\n"
            "    deepseek-search login\n\n"
            "  Or pass it explicitly:\n"
            "    export DEEPSEEK_API_KEY=sk-...\n"
            "    deepseek-search --api-key sk-... \"query\"\n"
        )
    return key
