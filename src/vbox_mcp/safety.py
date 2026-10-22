"""Confirmaciones, modo solo lectura y auditoría."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .config import Settings
from .vboxmanage import VBoxError

_SECRET_KEYS = {"password", "passwd", "secret", "token", "api_key", "apikey"}


class ConfirmationRequired(Exception):
    def __init__(self, action: str, target: str, effects: list[str]) -> None:
        super().__init__(
            f"La acción '{action}' sobre '{target}' requiere confirm=true."
        )
        self.action = action
        self.target = target
        self.effects = effects


def ensure_writable(settings: Settings) -> None:
    if settings.readonly:
        raise VBoxError(
            "El servidor está en modo solo lectura (VBOX_MCP_READONLY=true); "
            "esta operación no está permitida."
        )


def require_confirm(confirm: bool, action: str, target: str, effects: list[str]) -> None:
    if not confirm:
        raise ConfirmationRequired(action, target, effects)


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: ("***" if str(key).lower() in _SECRET_KEYS else redact(item))
            for key, item in value.items()
        }
    if isinstance(value, (list, tuple)):
        return [redact(item) for item in value]
    return value


def audit(
    settings: Settings,
    tool: str,
    args: dict[str, Any],
    result: str,
    duration_ms: int,
) -> None:
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "tool": tool,
        "args": redact(args),
        "result": result,
        "duration_ms": duration_ms,
    }
    try:
        path = Path(settings.audit_log)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        # La auditoría nunca debe tumbar la operación solicitada.
        pass
