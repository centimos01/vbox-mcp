"""Gestión de snapshots."""

from __future__ import annotations

from .config import Settings
from .vboxmanage import VBoxError, run, validate_vm


def _snapshot_name(name: str) -> str:
    value = name.strip()
    if not value or value.startswith("-"):
        raise VBoxError(f"Nombre de snapshot inválido: {name!r}")
    return value


def snapshot_take(
    settings: Settings,
    vm: str,
    name: str,
    description: str = "",
) -> dict[str, str]:
    vm = validate_vm(vm)
    name = _snapshot_name(name)
    args = ["snapshot", vm, "take", name]
    if description:
        args += ["--description", description]
    run(args, settings=settings)
    return {"vm": vm, "action": "snapshot_take", "name": name}


def snapshot_restore(settings: Settings, vm: str, name: str) -> dict[str, str]:
    vm = validate_vm(vm)
    name = _snapshot_name(name)
    run(["snapshot", vm, "restore", name], settings=settings)
    return {"vm": vm, "action": "snapshot_restore", "name": name}


def snapshot_delete(
    settings: Settings,
    vm: str,
    name: str,
    timeout: int | None = None,
) -> dict[str, str]:
    vm = validate_vm(vm)
    name = _snapshot_name(name)
    run(["snapshot", vm, "delete", name], settings=settings, timeout=timeout)
    return {"vm": vm, "action": "snapshot_delete", "name": name}
