"""Configuración del servidor a partir de variables de entorno."""

from __future__ import annotations

import os
import shutil
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping


def _standard_paths() -> list[Path]:
    if sys.platform == "win32":
        return [
            Path(r"C:\Program Files\Oracle\VirtualBox\VBoxManage.exe"),
            Path(r"C:\Program Files (x86)\Oracle\VirtualBox\VBoxManage.exe"),
        ]
    if sys.platform == "darwin":
        return [
            Path("/Applications/VirtualBox.app/Contents/MacOS/VBoxManage"),
            Path("/usr/local/bin/VBoxManage"),
            Path("/opt/homebrew/bin/VBoxManage"),
        ]
    return [Path("/usr/bin/VBoxManage"), Path("/usr/local/bin/VBoxManage")]


STANDARD_PATHS: list[Path] = _standard_paths()

_TRUE = {"1", "true", "yes", "on"}


def _as_bool(value: str | None, default: bool = False) -> bool:
    if value is None or value == "":
        return default
    return value.strip().lower() in _TRUE


def _default_audit_log() -> Path:
    if sys.platform == "win32":
        base = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local")
    else:
        base = Path(os.environ.get("XDG_STATE_HOME") or Path.home() / ".local" / "state")
    return base / "vbox-mcp" / "audit.log"


def find_vboxmanage(env: Mapping[str, str] | None = None) -> Path | None:
    """Localiza VBoxManage: variable de entorno, PATH y rutas estándar."""
    env = os.environ if env is None else env

    explicit = env.get("VBOX_MANAGE_PATH")
    if explicit:
        return Path(explicit)

    for name in ("VBoxManage", "VBoxManage.exe"):
        found = shutil.which(name)
        if found:
            return Path(found)

    for candidate in STANDARD_PATHS:
        try:
            if candidate.exists():
                return candidate
        except OSError:
            continue
    return None


@dataclass(frozen=True)
class Settings:
    vboxmanage_path: Path | None
    readonly: bool
    timeout_seconds: int
    audit_log: Path
    allow_mouse: bool
    guest_user: str | None
    guest_password: str | None

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> "Settings":
        env = os.environ if env is None else env

        timeout_raw = env.get("VBOX_MCP_TIMEOUT_SECONDS", "60")
        try:
            timeout = max(1, int(timeout_raw))
        except ValueError:
            timeout = 60

        audit_raw = env.get("VBOX_MCP_AUDIT_LOG")
        allow_mouse_raw = env.get("VBOX_MCP_ALLOW_MOUSE")

        return cls(
            vboxmanage_path=find_vboxmanage(env),
            readonly=_as_bool(env.get("VBOX_MCP_READONLY")),
            timeout_seconds=timeout,
            audit_log=Path(audit_raw) if audit_raw else _default_audit_log(),
            allow_mouse=_as_bool(allow_mouse_raw, default=True),
            guest_user=env.get("VBOX_MCP_GUEST_USER") or None,
            guest_password=env.get("VBOX_MCP_GUEST_PASSWORD") or None,
        )
