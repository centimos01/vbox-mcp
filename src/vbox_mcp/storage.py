"""Almacenamiento (ISOs, carpetas compartidas) y red NAT."""

from __future__ import annotations

import ipaddress
from pathlib import Path

from .config import Settings
from .parsing import parse_machine_readable, parse_nat_rules
from .vboxmanage import VBoxError, run, run_process, validate_vm

_PROTOCOLS = {"tcp", "udp"}


def _machine_info(settings: Settings, vm: str) -> dict[str, str]:
    result = run_process(["showvminfo", vm, "--machinereadable"], settings=settings)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "sin detalle"
        raise VBoxError(
            f"No se pudo consultar el estado de {vm}: {detail}",
            returncode=result.returncode,
            stderr=result.stderr,
        )
    return parse_machine_readable(result.stdout)


def _is_runtime(info: dict[str, str]) -> bool:
    return info.get("VMState") in {"running", "paused"}


def _shared_folder_names(info: dict[str, str], infix: str) -> set[str]:
    names: set[str] = set()
    for key, value in info.items():
        if key.startswith(f"SharedFolderName{infix}"):
            names.add(value)
    return names


def _validate_ip(label: str, value: str) -> str:
    value = value.strip()
    if not value:
        return ""
    if "," in value or any(char.isspace() for char in value):
        raise VBoxError(f"{label} no puede contener comas ni espacios: {value!r}")
    try:
        ipaddress.ip_address(value)
    except ValueError as exc:
        raise VBoxError(f"{label} no es una IP válida: {value!r}") from exc
    return value


def attach_iso(
    settings: Settings,
    vm: str,
    iso_path: str,
    controller: str = "sata",
    port: int = 1,
) -> dict[str, object]:
    vm = validate_vm(vm, settings)
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
    vm = validate_vm(vm, settings)
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
    vm = validate_vm(vm, settings)
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
    transient = _is_runtime(_machine_info(settings, vm))
    if transient:
        args.append("--transient")
    run(args, settings=settings)
    return {
        "vm": vm,
        "action": "shared_folder_add",
        "name": name,
        "host_path": str(folder),
        "transient": transient,
    }


def shared_folder_remove(settings: Settings, vm: str, name: str) -> dict[str, object]:
    vm = validate_vm(vm, settings)
    info = _machine_info(settings, vm)
    runtime = _is_runtime(info)
    transient = name in _shared_folder_names(info, "TransientMapping")
    if not transient:
        if name in _shared_folder_names(info, "MachineMapping"):
            if runtime:
                raise VBoxError(
                    f"La carpeta compartida {name!r} es persistente; apaga la VM para quitarla."
                )
        else:
            raise VBoxError(f"No existe la carpeta compartida {name!r} en {vm}.")
    args = ["sharedfolder", "remove", vm, "--name", name]
    if transient:
        args.append("--transient")
    run(args, settings=settings)
    return {"vm": vm, "action": "shared_folder_remove", "name": name, "transient": transient}


def nat_port_forward_add(
    settings: Settings,
    vm: str,
    rule_name: str,
    protocol: str,
    host_port: int,
    guest_port: int,
    guest_ip: str = "",
    host_ip: str = "",
) -> dict[str, object]:
    vm = validate_vm(vm, settings)
    protocol = protocol.lower()
    if protocol not in _PROTOCOLS:
        raise VBoxError(f"protocol debe ser uno de {sorted(_PROTOCOLS)}, no {protocol!r}")
    if not rule_name or "," in rule_name:
        raise VBoxError("rule_name no puede estar vacío ni contener comas")
    for label, port in (("host_port", host_port), ("guest_port", guest_port)):
        if not 1 <= int(port) <= 65535:
            raise VBoxError(f"{label} debe estar entre 1 y 65535")

    guest_ip = _validate_ip("guest_ip", guest_ip)
    host_ip = _validate_ip("host_ip", host_ip)

    rule = f"{rule_name},{protocol},{host_ip},{host_port},{guest_ip},{guest_port}"
    runtime = _is_runtime(_machine_info(settings, vm))
    if runtime:
        args = ["controlvm", vm, "natpf1", rule]
    else:
        args = ["modifyvm", vm, "--natpf1", rule]
    run(args, settings=settings)
    return {
        "vm": vm,
        "action": "nat_port_forward_add",
        "rule": rule,
    }


def nat_port_forward_remove(settings: Settings, vm: str, rule_name: str) -> dict[str, object]:
    vm = validate_vm(vm, settings)
    runtime = _is_runtime(_machine_info(settings, vm))
    if runtime:
        args = ["controlvm", vm, "natpf1", "delete", rule_name]
    else:
        args = ["modifyvm", vm, "--natpf1", "delete", rule_name]
    run(args, settings=settings)
    return {
        "vm": vm,
        "action": "nat_port_forward_remove",
        "rule": rule_name,
    }


def nat_list_rules(settings: Settings, vm: str) -> dict[str, object]:
    """Lista todas las reglas de reenvío de puertos NAT de una VM."""
    vm = validate_vm(vm, settings)
    info = _machine_info(settings, vm)
    rules = parse_nat_rules(info)
    return {"vm": vm, "rules": rules, "count": len(rules)}


def vrde_configure(
    settings: Settings,
    vm: str,
    enabled: bool = True,
    port: int = 3389,
    address: str = "",
    auth_type: str = "null",
    multi_connection: bool = False,
) -> dict[str, object]:
    """Configura el acceso remoto VRDE (RDP) de una VM."""
    vm = validate_vm(vm, settings)
    valid_auth = {"null", "external", "guest"}
    auth_type = auth_type.lower()
    if auth_type not in valid_auth:
        raise VBoxError(f"auth_type debe ser uno de {sorted(valid_auth)}, no {auth_type!r}")
    if not 1 <= port <= 65535:
        raise VBoxError("port debe estar entre 1 y 65535")

    args = [
        "modifyvm",
        vm,
        "--vrde",
        "on" if enabled else "off",
        "--vrde-port",
        str(port),
        "--vrde-auth-type",
        auth_type,
        "--vrde-multicon",
        "on" if multi_connection else "off",
    ]
    if address:
        args += ["--vrde-address", address]
    run(args, settings=settings)
    return {
        "vm": vm,
        "action": "vrde_configure",
        "enabled": enabled,
        "port": port,
        "auth_type": auth_type,
        "multi_connection": multi_connection,
    }

