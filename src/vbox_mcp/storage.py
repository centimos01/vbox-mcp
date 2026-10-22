"""Almacenamiento (ISOs, carpetas compartidas) y red NAT."""

from __future__ import annotations

from pathlib import Path

from .config import Settings
from .vboxmanage import VBoxError, run, validate_vm

_PROTOCOLS = {"tcp", "udp"}


def attach_iso(
    settings: Settings,
    vm: str,
    iso_path: str,
    controller: str = "sata",
    port: int = 1,
) -> dict[str, object]:
    vm = validate_vm(vm)
    iso = Path(iso_path)
    if not iso.is_file():
        raise VBoxError(f"No existe el ISO: {iso_path}")
    run(
        [
            "storageattach",
            vm,
            "--storagectl",
            controller,
            "--port",
            str(port),
            "--device",
            "0",
            "--type",
            "dvddrive",
            "--medium",
            str(iso),
        ],
        settings=settings,
    )
    return {"vm": vm, "action": "attach_iso", "iso": str(iso), "controller": controller, "port": port}


def detach_iso(
    settings: Settings,
    vm: str,
    controller: str = "sata",
    port: int = 1,
) -> dict[str, object]:
    vm = validate_vm(vm)
    run(
        [
            "storageattach",
            vm,
            "--storagectl",
            controller,
            "--port",
            str(port),
            "--device",
            "0",
            "--type",
            "dvddrive",
            "--medium",
            "none",
        ],
        settings=settings,
    )
    return {"vm": vm, "action": "detach_iso", "controller": controller, "port": port}


def shared_folder_add(
    settings: Settings,
    vm: str,
    name: str,
    host_path: str,
    automount: bool = True,
    readonly: bool = False,
) -> dict[str, object]:
    vm = validate_vm(vm)
    folder = Path(host_path)
    if not folder.exists():
        raise VBoxError(f"No existe host_path: {host_path}")

    args = [
        "sharedfolder",
        "add",
        vm,
        "--name",
        name,
        "--hostpath",
        str(folder),
    ]
    if automount:
        args.append("--automount")
    if readonly:
        args.append("--readonly")
    run(args, settings=settings)
    return {"vm": vm, "action": "shared_folder_add", "name": name, "host_path": str(folder)}


def shared_folder_remove(settings: Settings, vm: str, name: str) -> dict[str, object]:
    vm = validate_vm(vm)
    run(["sharedfolder", "remove", vm, "--name", name], settings=settings)
    return {"vm": vm, "action": "shared_folder_remove", "name": name}


def nat_port_forward_add(
    settings: Settings,
    vm: str,
    rule_name: str,
    protocol: str,
    host_port: int,
    guest_port: int,
    guest_ip: str = "",
) -> dict[str, object]:
    vm = validate_vm(vm)
    protocol = protocol.lower()
    if protocol not in _PROTOCOLS:
        raise VBoxError(f"protocol debe ser uno de {sorted(_PROTOCOLS)}, no {protocol!r}")
    if not rule_name or "," in rule_name:
        raise VBoxError("rule_name no puede estar vacío ni contener comas")
    for label, port in (("host_port", host_port), ("guest_port", guest_port)):
        if not 1 <= int(port) <= 65535:
            raise VBoxError(f"{label} debe estar entre 1 y 65535")

    rule = f"{rule_name},{protocol},,{host_port},{guest_ip},{guest_port}"
    run(["modifyvm", vm, "--natpf1", rule], settings=settings)
    return {"vm": vm, "action": "nat_port_forward_add", "rule": rule}


def nat_port_forward_remove(settings: Settings, vm: str, rule_name: str) -> dict[str, object]:
    vm = validate_vm(vm)
    run(["modifyvm", vm, "--natpf1", "delete", rule_name], settings=settings)
    return {"vm": vm, "action": "nat_port_forward_remove", "rule": rule_name}
