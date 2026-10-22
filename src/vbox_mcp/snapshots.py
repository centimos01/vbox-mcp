"""Gestión de snapshots."""

from __future__ import annotations

from .config import Settings
from .vboxmanage import run, validate_vm


def snapshot_take(
    settings: Settings,
    vm: str,
    name: str,
    description: str = "",
) -> dict[str, str]:
    vm = validate_vm(vm)
    args = ["snapshot", vm, "take", name]
    if description:
        args += ["--description", description]
    run(args, settings=settings)
    return {"vm": vm, "action": "snapshot_take", "name": name}


def snapshot_restore(settings: Settings, vm: str, name: str) -> dict[str, str]:
    vm = validate_vm(vm)
    run(["snapshot", vm, "restore", name], settings=settings)
    return {"vm": vm, "action": "snapshot_restore", "name": name}


def snapshot_delete(settings: Settings, vm: str, name: str) -> dict[str, str]:
    vm = validate_vm(vm)
    run(["snapshot", vm, "delete", name], settings=settings)
    return {"vm": vm, "action": "snapshot_delete", "name": name}
