"""Ejecución de VBoxManage y consultas de solo lectura."""

from __future__ import annotations

import locale
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .parsing import (
    parse_blocks,
    parse_machine_readable,
    parse_ostypes,
    parse_snapshots,
    parse_vm_list,
    parse_nat_rules,
    parse_shared_folders,
    parse_attached_disks,
)

MAX_OUTPUT_CHARS = 1024 * 1024


class VBoxError(RuntimeError):
    def __init__(self, message: str, returncode: int | None = None, stderr: str = "") -> None:
        super().__init__(message)
        self.returncode = returncode
        self.stderr = stderr


@dataclass
class CommandResult:
    args: list[str]
    returncode: int
    stdout: str
    stderr: str


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8", locale.getpreferredencoding(False), "cp1252"):
        try:
            return raw.decode(encoding)[:MAX_OUTPUT_CHARS]
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace")[:MAX_OUTPUT_CHARS]


def validate_vm(vm: str, settings: Settings | None = None) -> str:
    if not isinstance(vm, str):
        raise VBoxError("El identificador de VM debe ser texto.")
    value = vm.strip()
    if not value or value.startswith("-"):
        raise VBoxError(f"Identificador de VM inválido: {vm!r}")
    if settings:
        for pattern in settings.dangerous_vm_patterns:
            import fnmatch
            if fnmatch.fnmatch(value, pattern):
                raise VBoxError(f"Nombre de VM coincide con patrón peligroso: {pattern!r}")
    return value


def run_process(
    args: list[str],
    *,
    timeout: int | None = None,
    settings: Settings | None = None,
) -> CommandResult:
    settings = settings or Settings.from_env()
    if settings.vboxmanage_path is None:
        raise VBoxError(
            "No se encontró VBoxManage. Define VBOX_MANAGE_PATH o instala VirtualBox."
        )

    command = [str(settings.vboxmanage_path), *[str(arg) for arg in args]]
    timeout = timeout or settings.timeout_seconds
    creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0

    try:
        completed = subprocess.run(
            command,
            capture_output=True,
            timeout=timeout,
            creationflags=creationflags,
            stdin=subprocess.DEVNULL,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise VBoxError(
            f"VBoxManage excedió el timeout de {timeout} s ejecutando: {' '.join(args[:4])}"
        ) from exc
    except (FileNotFoundError, OSError) as exc:
        raise VBoxError(
            f"No se pudo ejecutar VBoxManage en {settings.vboxmanage_path}: {exc}"
        ) from exc

    return CommandResult(
        args=args,
        returncode=completed.returncode,
        stdout=_decode(completed.stdout),
        stderr=_decode(completed.stderr),
    )


def run(
    args: list[str],
    *,
    timeout: int | None = None,
    settings: Settings | None = None,
) -> str:
    result = run_process(args, timeout=timeout, settings=settings)
    if result.returncode != 0:
        detail = result.stderr.strip() or result.stdout.strip() or "sin detalle"
        raise VBoxError(
            f"VBoxManage falló con código {result.returncode}: {detail}",
            returncode=result.returncode,
            stderr=result.stderr,
        )
    return result.stdout


def list_vms(settings: Settings, running_only: bool = False) -> list[dict[str, str]]:
    if running_only:
        return [
            {**vm, "state": "running"}
            for vm in parse_vm_list(run(["list", "runningvms"], settings=settings))
        ]

    vms = parse_vm_list(run(["list", "vms"], settings=settings))
    running_uuids = {
        vm["uuid"] for vm in parse_vm_list(run(["list", "runningvms"], settings=settings))
    }
    result = []
    for vm in vms:
        vm_data = {**vm, "state": "running" if vm["uuid"] in running_uuids else "stopped"}
        # Get group and description from showvminfo
        try:
            raw = parse_machine_readable(
                run(["showvminfo", validate_vm(vm["uuid"], settings), "--machinereadable"], settings=settings)
            )
            vm_data["group"] = raw.get("groups", "/").strip() or "/"
            vm_data["description"] = raw.get("description", "").strip()
        except (VBoxError, OSError):
            vm_data["group"] = "/"
            vm_data["description"] = ""
        result.append(vm_data)
    return result


def _as_int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def vm_info(settings: Settings, vm: str) -> dict[str, object]:
    vm = validate_vm(vm, settings)
    raw = parse_machine_readable(
        run(["showvminfo", vm, "--machinereadable"], settings=settings)
    )
    summary = {
        "name": raw.get("name", vm),
        "uuid": raw.get("UUID"),
        "state": raw.get("VMState"),
        "cpus": _as_int(raw.get("cpus")),
        "memory_mb": _as_int(raw.get("memory")),
        "ostype": raw.get("ostype"),
        "guest_additions": raw.get("GuestAdditionsVersion"),
    }
    return {"summary": summary, "raw": raw}


def list_ostypes(settings: Settings) -> list[dict[str, str]]:
    return parse_ostypes(run(["list", "ostypes"], settings=settings))


def snapshot_list(settings: Settings, vm: str) -> list[dict[str, object]]:
    vm = validate_vm(vm, settings)
    return parse_snapshots(
        run(["snapshot", vm, "list", "--machinereadable"], settings=settings)
    )


def list_networks(settings: Settings) -> dict[str, list[dict[str, str]]]:
    hostonly = parse_blocks(
        run(["list", "hostonlyifs", "--machinereadable"], settings=settings)
    )
    natnets = parse_blocks(
        run(["list", "natnets", "--machinereadable"], settings=settings)
    )
    return {"hostonly": hostonly, "natnets": natnets}


def guest_ip(settings: Settings, vm: str) -> str | None:
    vm = validate_vm(vm, settings)
    result = run_process(
        ["guestproperty", "get", vm, "/VirtualBox/GuestInfo/Net/0/V4/IP"],
        settings=settings,
    )
    if result.returncode != 0:
        return None
    for line in result.stdout.splitlines():
        if line.startswith("Value:"):
            value = line.split(":", 1)[1].strip()
            return value or None
    return None


def guest_ips(settings: Settings, vm: str) -> list[dict[str, str]]:
    """Devuelve todas las IPs reportadas por Guest Additions (todas las NICs)."""
    vm = validate_vm(vm, settings)
    ips: list[dict[str, str]] = []
    for nic_index in range(8):
        for version in ("V4", "V6"):
            result = run_process(
                [
                    "guestproperty",
                    "get",
                    vm,
                    f"/VirtualBox/GuestInfo/Net/{nic_index}/{version}/IP",
                ],
                settings=settings,
            )
            if result.returncode != 0:
                break
            for line in result.stdout.splitlines():
                if line.startswith("Value:"):
                    value = line.split(":", 1)[1].strip()
                    if value and value != "no value":
                        ips.append({"nic": str(nic_index), "version": version, "ip": value})
    return ips


def host_info(settings: Settings) -> dict[str, object]:
    """Devuelve información del host desde VBoxManage list hostinfo."""
    result = run_process(["list", "hostinfo"], settings=settings)
    if result.returncode != 0:
        raise VBoxError(
            f"No se pudo obtener info del host: {result.stderr.strip() or result.stdout.strip()}"
        )
    info: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            info[key.strip().lower().replace(" ", "_")] = value.strip()
    return {"host_info": info}


def vm_info_extended(settings: Settings, vm: str) -> dict[str, object]:
    """Devuelve vm_info enriquecido con discos adjuntos, reglas NAT y carpetas compartidas."""
    vm = validate_vm(vm, settings)
    raw = parse_machine_readable(
        run(["showvminfo", vm, "--machinereadable"], settings=settings)
    )

    summary = {
        "name": raw.get("name", vm),
        "uuid": raw.get("UUID"),
        "state": raw.get("VMState"),
        "cpus": _as_int(raw.get("cpus")),
        "memory_mb": _as_int(raw.get("memory")),
        "vram_mb": _as_int(raw.get("vram")),
        "ostype": raw.get("ostype"),
        "description": raw.get("description", ""),
        "guest_additions": raw.get("GuestAdditionsVersion"),
        "groups": raw.get("groups", "/"),
        "boot_order": [
            raw.get(f"boot{i}", "none") for i in range(1, 5)
            if raw.get(f"boot{i}", "none") != "none"
        ],
    }

    return {
        "summary": summary,
        "nat_rules": parse_nat_rules(raw),
        "shared_folders": parse_shared_folders(raw),
        "attached_disks": parse_attached_disks(raw),
        "raw": raw,
    }


def wait_for_state(
    settings: Settings,
    vm: str,
    target_state: str,
    timeout_seconds: int = 120,
    poll_interval: float = 2.0,
) -> dict[str, object]:
    """Espera a que la VM alcance el estado indicado (running, stopped, paused, saved)."""
    vm = validate_vm(vm, settings)
    valid_states = {"running", "stopped", "paused", "saved", "aborted", "poweroff"}
    target_state = target_state.lower()
    if target_state not in valid_states:
        raise VBoxError(f"target_state debe ser uno de {sorted(valid_states)}, no {target_state!r}")

    deadline = time.monotonic() + timeout_seconds
    last_state = "unknown"
    while time.monotonic() < deadline:
        result = run_process(
            ["showvminfo", vm, "--machinereadable"],
            settings=settings,
        )
        if result.returncode == 0:
            raw = parse_machine_readable(result.stdout)
            last_state = raw.get("VMState", "unknown").lower()
            # VBox reports "poweroff" for stopped VMs sometimes
            if last_state in (target_state, f'"{target_state}"'):
                return {"vm": vm, "state": last_state, "reached": True}
            if target_state == "stopped" and last_state in {"poweroff", "aborted"}:
                return {"vm": vm, "state": last_state, "reached": True}
        time.sleep(poll_interval)

    return {
        "vm": vm,
        "state": last_state,
        "reached": False,
        "note": f"Timeout: la VM no alcanzó '{target_state}' en {timeout_seconds}s.",
    }


def list_groups(settings: Settings) -> dict[str, object]:
    """Lista los grupos de VMs configurados en VirtualBox."""
    result = run_process(["list", "groups"], settings=settings)
    if result.returncode != 0:
        raise VBoxError(
            f"No se pudo listar grupos: {result.stderr.strip() or result.stdout.strip()}"
        )
    groups = [line.strip().strip('"') for line in result.stdout.splitlines() if line.strip()]
    return {"groups": groups}
