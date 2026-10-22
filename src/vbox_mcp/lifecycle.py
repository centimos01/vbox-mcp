"""Operaciones de ciclo de vida de máquinas virtuales."""

from __future__ import annotations

from pathlib import Path

from .config import Settings
from .parsing import parse_machine_readable
from .snapshots import validate_snapshot_name
from .storage import attach_iso
from .vboxmanage import VBoxError, run, validate_vm

_START_MODES = {"headless", "gui", "separate"}
_STOP_MODES = {"acpi", "poweroff", "save"}
_NIC_MODES = {"nat", "bridged", "hostonly", "none", "intnet", "natnetwork"}
_SATA_CONTROLLER = "sata"
_BOOT_DEVICES = {"dvd", "disk", "net", "none"}


def start_vm(settings: Settings, vm: str, mode: str = "headless") -> dict[str, str]:
    vm = validate_vm(vm, settings)
    if mode not in _START_MODES:
        raise VBoxError(f"mode debe ser uno de {sorted(_START_MODES)}, no {mode!r}")
    run(["startvm", vm, "--type", mode], settings=settings)
    return {"vm": vm, "action": "start", "mode": mode}


def stop_vm(settings: Settings, vm: str, mode: str = "acpi") -> dict[str, str]:
    vm = validate_vm(vm, settings)
    if mode not in _STOP_MODES:
        raise VBoxError(f"mode debe ser uno de {sorted(_STOP_MODES)}, no {mode!r}")
    command = {"acpi": "acpipowerbutton", "poweroff": "poweroff", "save": "savestate"}[mode]
    run(["controlvm", vm, command], settings=settings)
    return {"vm": vm, "action": "stop", "mode": mode}


def pause_vm(settings: Settings, vm: str) -> dict[str, str]:
    vm = validate_vm(vm, settings)
    run(["controlvm", vm, "pause"], settings=settings)
    return {"vm": vm, "action": "pause"}


def resume_vm(settings: Settings, vm: str) -> dict[str, str]:
    vm = validate_vm(vm, settings)
    run(["controlvm", vm, "resume"], settings=settings)
    return {"vm": vm, "action": "resume"}


def reset_vm(settings: Settings, vm: str) -> dict[str, str]:
    vm = validate_vm(vm, settings)
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
    adapter: str = "",
) -> dict[str, object]:
    vm = validate_vm(name)
    if network not in _NIC_MODES:
        raise VBoxError(f"network debe ser uno de {sorted(_NIC_MODES)}, no {network!r}")
    if network in {"bridged", "hostonly"} and not adapter:
        raise VBoxError(
            f"network={network!r} requiere adapter (nombre de la interfaz del host)."
        )
    if cpus < 1 or memory_mb < 128:
        raise VBoxError("cpus debe ser >= 1 y memory_mb >= 128")

    run(["createvm", "--name", vm, "--ostype", ostype, "--register"], settings=settings)
    modify_args = [
        "modifyvm",
        vm,
        "--cpus",
        str(cpus),
        "--memory",
        str(memory_mb),
        "--nic1",
        network,
    ]
    if adapter and network in {"bridged", "hostonly"}:
        flag = "--bridgeadapter1" if network == "bridged" else "--hostonlyadapter1"
        modify_args += [flag, adapter]
    run(modify_args, settings=settings)

    disk_path: str | None = None
    has_sata = False
    if disk_mb and disk_mb > 0:
        raw = parse_machine_readable(
            run(["showvminfo", vm, "--machinereadable"], settings=settings)
        )
        cfg = raw.get("CfgFile")
        if not cfg:
            raise VBoxError(f"No se pudo determinar la carpeta de configuración de {vm}")
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
    vram_mb: int | None = None,
    nic: str | None = None,
    adapter: str | None = None,
    description: str | None = None,
    boot_order: list[str] | None = None,
) -> dict[str, object]:
    vm = validate_vm(vm, settings)
    args = ["modifyvm", vm]
    if cpus is not None:
        args += ["--cpus", str(cpus)]
    if memory_mb is not None:
        args += ["--memory", str(memory_mb)]
    if vram_mb is not None:
        if not 1 <= vram_mb <= 256:
            raise VBoxError("vram_mb debe estar entre 1 y 256")
        args += ["--vram", str(vram_mb)]
    if nic is not None:
        if nic not in _NIC_MODES:
            raise VBoxError(f"nic debe ser uno de {sorted(_NIC_MODES)}, no {nic!r}")
        if nic in {"bridged", "hostonly"} and not adapter:
            raise VBoxError(f"nic={nic!r} requiere adapter (nombre de la interfaz del host).")
        args += ["--nic1", nic]
        if adapter and nic in {"bridged", "hostonly"}:
            flag = "--bridgeadapter1" if nic == "bridged" else "--hostonlyadapter1"
            args += [flag, adapter]
    if description is not None:
        args += ["--description", description]
    if boot_order is not None:
        for i, dev in enumerate(boot_order[:4], 1):
            dev = dev.lower()
            if dev not in _BOOT_DEVICES:
                raise VBoxError(f"boot device debe ser uno de {sorted(_BOOT_DEVICES)}, no {dev!r}")
            args += [f"--boot{i}", dev]
    if len(args) == 2:
        raise VBoxError("Debes indicar al menos un cambio (cpus, memory_mb, vram_mb, nic, description o boot_order).")
    run(args, settings=settings)
    return {"vm": vm, "action": "modify", "changes": args[2:]}


def clone_vm(
    settings: Settings,
    source: str,
    name: str,
    mode: str = "full",
    snapshot: str | None = None,
    timeout: int | None = None,
) -> dict[str, str]:
    source = validate_vm(source)
    name = validate_vm(name)
    if mode not in {"full", "linked"}:
        raise VBoxError("mode debe ser 'full' o 'linked'")
    if mode == "linked" and not snapshot:
        raise VBoxError(
            "mode='linked' requiere snapshot: VirtualBox solo crea clones enlazados desde un snapshot."
        )
    if snapshot:
        snapshot = validate_snapshot_name(snapshot)

    args = ["clonevm", source, "--name", name, "--register"]
    if mode == "full":
        args += ["--mode", "machine"]
    else:
        args += ["--mode", "machine", "--options", "link"]
    if snapshot:
        args += ["--snapshot", snapshot]

    run(args, settings=settings, timeout=timeout)
    return {"source": source, "name": name, "mode": mode}


def delete_vm(
    settings: Settings,
    vm: str,
    delete_disks: bool = False,
    timeout: int | None = None,
) -> dict[str, object]:
    vm = validate_vm(vm, settings)
    args = ["unregistervm", vm]
    if delete_disks:
        args.append("--delete")
    run(args, settings=settings, timeout=timeout)
    return {"vm": vm, "action": "delete", "delete_disks": delete_disks}


def group_vms(
    settings: Settings,
    vms: list[str],
    group: str,
) -> dict[str, object]:
    """Asigna una lista de VMs a un grupo VirtualBox."""
    if not group.startswith("/"):
        group = f"/{group}"
    validated = [validate_vm(vm, settings) for vm in vms]
    results: list[dict[str, object]] = []
    for vm in validated:
        run(["modifyvm", vm, "--groups", group], settings=settings)
        results.append({"vm": vm, "group": group})
    return {"action": "group_vms", "group": group, "vms": results}


def add_storage_controller(
    settings: Settings,
    vm: str,
    name: str,
    bus: str = "sata",
    controller: str = "IntelAhci",
) -> dict[str, object]:
    """Añade un controlador de almacenamiento a una VM."""
    vm = validate_vm(vm, settings)
    valid_buses = {"sata", "ide", "scsi", "usb", "pcie", "nvme"}
    bus = bus.lower()
    if bus not in valid_buses:
        raise VBoxError(f"bus debe ser uno de {sorted(valid_buses)}, no {bus!r}")
    run(
        ["storagectl", vm, "--name", name, "--add", bus, "--controller", controller],
        settings=settings,
    )
    return {"vm": vm, "action": "add_storage_controller", "name": name, "bus": bus}


def snapshot_rename(
    settings: Settings,
    vm: str,
    old_name: str,
    new_name: str,
    description: str = "",
) -> dict[str, object]:
    """Renombra un snapshot existente."""
    from .snapshots import validate_snapshot_name
    vm = validate_vm(vm, settings)
    old_name = validate_snapshot_name(old_name)
    new_name = validate_snapshot_name(new_name)
    args = ["snapshot", vm, "edit", old_name, "--name", new_name]
    if description:
        args += ["--description", description]
    run(args, settings=settings)
    return {"vm": vm, "action": "snapshot_rename", "old_name": old_name, "new_name": new_name}

