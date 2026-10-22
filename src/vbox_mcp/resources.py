"""MCP Resources para health check y versión."""

from __future__ import annotations

import os
from pathlib import Path

from .config import Settings
from .vboxmanage import VBoxError, run, run_process, host_info


async def health_check(settings: Settings) -> dict:
    """Health check del servidor MCP y VirtualBox."""
    checks: dict[str, object] = {
        "mcp_server": "ok",
        "vboxmanage": "unknown",
    }

    # Verificar VBoxManage
    try:
        result = run_process(["--version"], settings=settings)
        if result.returncode == 0:
            checks["vboxmanage"] = {
                "status": "ok",
                "version": result.stdout.strip(),
                "path": str(settings.vboxmanage_path),
            }
        else:
            checks["vboxmanage"] = {
                "status": "error",
                "error": result.stderr.strip() or result.stdout.strip() or "sin detalle",
            }
    except (VBoxError, OSError) as exc:
        checks["vboxmanage"] = {"status": "error", "error": str(exc)}

    # Verificar audit log
    audit_path = Path(settings.audit_log)
    checks["audit_log"] = {
        "path": str(audit_path),
        "exists": audit_path.exists(),
        "writable": audit_path.parent.exists() and os.access(audit_path.parent, os.W_OK),
    }

    overall = "ok" if all(
        isinstance(v, str) and v == "ok" or
        isinstance(v, dict) and v.get("status") == "ok"
        for v in checks.values()
    ) else "degraded"

    return {"status": overall, "checks": checks}


async def version_info(settings: Settings) -> dict:
    """Información de versión del servidor y VBoxManage."""
    vbox_version = "unknown"
    try:
        result = run_process(["--version"], settings=settings)
        if result.returncode == 0:
            vbox_version = result.stdout.strip()
    except (VBoxError, OSError):
        pass

    return {
        "server": {
            "name": "vbox-mcp",
            "version": "0.2.0",
            "protocol": "MCP",
        },
        "vboxmanage": {
            "version": vbox_version,
            "path": str(settings.vboxmanage_path) if settings.vboxmanage_path else None,
        },
        "config": {
            "readonly": settings.readonly,
            "timeout_seconds": settings.timeout_seconds,
            "audit_log": str(settings.audit_log),
            "allow_mouse": settings.allow_mouse,
        },
    }


async def host_info_resource(settings: Settings) -> dict:
    """Información del host desde VBoxManage."""
    try:
        info = host_info(settings)
        return {"status": "ok", "data": info}
    except VBoxError as exc:
        return {"status": "error", "error": str(exc)}


