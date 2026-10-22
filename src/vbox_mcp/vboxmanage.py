"""Ejecución de VBoxManage y consultas de solo lectura."""

from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

from .config import Settings
from .parsing import parse_blocks, parse_machine_readable, parse_ostypes, parse_snapshots, parse_vm_list

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
    return raw.decode("utf-8", errors="replace")[:MAX_OUTPUT_CHARS]


def validate_vm(vm: str) -> str:
    if not isinstance(vm, str):
        raise VBoxError("El identificador de VM debe ser texto.")
    value = vm.strip()
    if not value or value.startswith("-"):
        raise VBoxError(f"Identificador de VM inválido: {vm!r}")
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
    return [
        {**vm, "state": "running" if vm["uuid"] in running_uuids else "stopped"}
        for vm in vms
    ]


def _as_int(value: str | None) -> int | None:
    try:
        return int(value) if value is not None else None
    except ValueError:
        return None


def vm_info(settings: Settings, vm: str) -> dict[str, object]:
    vm = validate_vm(vm)
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
    vm = validate_vm(vm)
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
    vm = validate_vm(vm)
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
