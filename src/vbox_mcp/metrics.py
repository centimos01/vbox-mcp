"""Métricas ligeras y lectura del audit log."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .config import Settings


def read_audit_log(
    settings: Settings,
    last_n: int = 50,
    tool_filter: str = "",
    result_filter: str = "",
) -> dict[str, object]:
    """Lee las últimas N entradas del audit log JSONL."""
    path = Path(settings.audit_log)
    if not path.exists():
        return {"entries": [], "total": 0, "log_path": str(path), "note": "Log no existe aún."}

    lines: list[str] = []
    try:
        with path.open("r", encoding="utf-8") as fh:
            lines = fh.readlines()
    except OSError as exc:
        return {"entries": [], "error": str(exc), "log_path": str(path)}

    entries: list[dict[str, Any]] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if tool_filter and entry.get("tool") != tool_filter:
            continue
        if result_filter and entry.get("result") != result_filter:
            continue
        entries.append(entry)

    total = len(entries)
    last_n = max(1, min(1000, int(last_n)))
    return {
        "entries": entries[-last_n:],
        "total": total,
        "showing": min(last_n, total),
        "log_path": str(path),
    }


def audit_stats(settings: Settings) -> dict[str, object]:
    """Calcula estadísticas simples del audit log: llamadas por tool y duración media."""
    path = Path(settings.audit_log)
    if not path.exists():
        return {"tools": {}, "total_calls": 0}

    from collections import defaultdict

    counts: dict[str, int] = defaultdict(int)
    durations: dict[str, list[int]] = defaultdict(list)
    errors: dict[str, int] = defaultdict(int)

    try:
        with path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                tool = entry.get("tool", "unknown")
                counts[tool] += 1
                ms = entry.get("duration_ms")
                if isinstance(ms, (int, float)):
                    durations[tool].append(int(ms))
                if str(entry.get("result", "")).startswith("error"):
                    errors[tool] += 1
    except OSError:
        return {"tools": {}, "total_calls": 0}

    tools: dict[str, dict[str, object]] = {}
    for tool, count in counts.items():
        dur = durations[tool]
        tools[tool] = {
            "calls": count,
            "errors": errors.get(tool, 0),
            "avg_ms": int(sum(dur) / len(dur)) if dur else 0,
            "max_ms": max(dur) if dur else 0,
        }

    return {
        "tools": tools,
        "total_calls": sum(counts.values()),
        "total_errors": sum(errors.values()),
    }
