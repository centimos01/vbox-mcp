"""Operaciones de ciclo de vida de mÃ¡quinas virtuales."""

from __future__ import annotations

from pathlib import Path

from .config import Settings
from .parsing import parse_machine_readable
from .storage import attach_iso
from .vboxmanage import VBoxError, run, validate_vm

_START_MODES = {"headless", "gui"}
_STOP_MODES = {"acpi", "poweroff", "save"}
_NIC_MODES = {"nat", "bridged", "hostonly", "none"}
_SATA_CONTROLLER = "sata"


def start_vm(settings: Settings, vm: str, mode: str = "headless") -> dict[str, str]:
    vm = validate_vm(vm)
    if mode not in _START_MODES:
        raise VBoxError(f"mode debe ser uno de {sorted(_START_MODES)}, no {mode!r}")
    run(["startvm", vm, "--type", mode], settings=settings)
    return {"vm": vm, "action": "start", "mode": mode}


def stop_vm(settings: Settings, vm: str, mode: str = "acpi") -> dict[str, str]:
    vm = validate_vm(vm)
    if mode not in _STOP_MODES:
        raise VBoxError(f"mode debe ser uno de {sorted(_STOP_MODES)}, no {mode!r}")
    command = {"acpi": "acpipowerbutton", "poweroff": "poweroff", "save": "savestate"}[mode]
    run(["controlvm", vm, command], settings=settings)
    return {"vm": vm, "action": "stop", "mode": mode}


def pause_vm(settings: Settings, vm: str) -> dict[str, str]:
    vm = validate_vm(vm)
    run(["controlvm", vm, "pause"], settings=settings)
    return {"vm": vm, "action": "pause"}


def resume_vm(settings: Settings, vm: str) -> dict[str, str]:
    vm = validate_vm(vm)
    run(["controlvm", vm, "resume"], settings=settings)
    return {"vm": vm, "action": "resume"}


def reset_vm(settings: Settings, vm: str) -> dict[str, str]:
    vm = validate_vm(vm)
    run(["controlvm", vm, "reset"], settings=settings)
    return {"vm": vm, "action": "reset"}


def create_vm(
    settings: Settings,
    name: str,
    ostype: str,
    cpus: int = 2,
    memory_mb: int = 2048,
    disk_mb: int = 0,
    iso: str | None = None,
    network: str = "nat",
) -> dict[str, object]:
    vm = validate_vm(name)
    if network not in _NIC_MODES:
        raise VBoxError(f"network debe ser uno de {sorted(_NIC_MODES)}, no {network!r}")
    if cpus < 1 or memory_mb < 128:
        raise VBoxError("cpus debe ser >= 1 y memory_mb >= 128")

    run(["createvm", "--name", vm, "--ostype", ostype, "--register"], settings=settings)
    run(
        [
            "modifyvm",
            vm,
            "--cpus",
            str(cpus),
            "--memory",
            str(memory_mb),
            "--nic1",
            network,
        ],
        settings=settings,
    )

    disk_path: str | None = None
    has_sata = False
    if disk_mb and disk_mb > 0:
        raw = parse_machine_readable(
            run(["showvminfo", vm, "--machinereadable"], settings=settings)
        )
        cfg = raw.get("CfgFile")
        if not cfg:
            raise VBoxError(f"No se pudo determinar la carpeta de configuraciÃ³n de {vm}")
        disk = Path(cfg).parent / f"{vm}.vdi"
        run(
            [
                "createmedium",
                "disk",
                "--filename",
                str(disk),
                "--size",
                str(disk_mb),
                "--format",
                "VDI",
            ],
            settings=settings,
        )
        run(
            ["storagectl", vm, "--name", _SATA_CONTROLLER, "--add", "sata", "--controller", "IntelAhci"],
            settings=settings,
        )
        has_sata = True
        run(
            [
                "storageattach",
                vm,
                "--storagectl",
                _SATA_CONTROLLER,
                "--port",
                "0",
                "--device",
                "0",
                "--type",
                "hdd",
                "--medium",
                str(disk),
            ],
            settings=settings,
        )
        disk_path = str(disk)

    if iso:
        if not has_sata:
            run(
                ["storagectl", vm, "--name", _SATA_CONTROLLER, "--add", "sata", "--controller", "IntelAhci"],
                settings=settings,
            )
        attach_iso(settings, vm, iso, controller=_SATA_CONTROLLER)

    return {"name": vm, "disk": disk_path, "iso": iso}


def modify_vm(
    settings: Settings,
    vm: str,
    cpus: int | None = None,
    memory_mb: int | None = None,
    nic: str | None = None,
) -> dict[str, object]:
    vm = validate_vm(vm)
    args = ["modifyvm", vm]
    if cpus is not None:
        args += ["--cpus", str(cpus)]
    if memory_mb is not None:
        args += ["--memory", str(memory_mb)]
    if nic is not None:
        if nic not in _NIC_MODES:
            raise VBoxError(f"nic debe ser uno de {sorted(_NIC_MODES)}, no {nic!r}")
        args += ["--nic1", nic]
    if len(args) == 2:
        raise VBoxError("Debes indicar al menos un cambio (cpus, memory_mb o nic).")
    run(args, settings=settings)
    return {"vm": vm, "action": "modify", "changes": args[2:]}


def clone_vm(
    settings: Settings,
    source: str,
    name: str,
    mode: str = "full",
    snapshot: str | None = None,
) -> dict[str, str]:
    source = validate_vm(source)
    name = validate_vm(name)
    if mode not in {"full", "linked"}:
        raise VBoxError("mode debe ser 'full' o 'linked'")

    args = ["clonevm", source, "--name", name, "--register"]
    if mode == "full":
        args += ["--mode", "all"]
    else:
        args += ["--mode", "machine", "--options", "link"]
    if snapshot:
        args += ["--snapshot", snapshot]

    run(args, settings=settings)
    return {"source": source, "name": name, "mode": mode}


def delete_vm(settings: Settings, vm: str, delete_disks: bool = False) -> dict[str, object]:
    vm = validate_vm(vm)
    args = ["unregistervm", vm]
    if delete_disks:
        args.append("--delete")
    run(args, settings=settings)
    return {"vm": vm, "action": "delete", "delete_disks": delete_disks}

