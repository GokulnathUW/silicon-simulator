"""Load settings from the repository .env file."""

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent


def load_env() -> None:
    """Load .env from the repository root into the process environment."""
    load_dotenv(ROOT / ".env")


def setting(name: str) -> str:
    """Return a required setting from the environment."""
    load_env()
    value = os.getenv(name, "").strip()
    if not value:
        raise RuntimeError(f"Set {name} in .env")
    return value


def setting_path(name: str) -> Path:
    """Return a path setting. Relative paths start at the repository root."""
    path = Path(setting(name)).expanduser()
    if not path.is_absolute():
        path = ROOT / path
    return path
