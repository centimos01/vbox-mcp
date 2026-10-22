"""Ejecución y transferencia de archivos dentro del guest (Guest Additions)."""

from __future__ import annotations

import os
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from .config import Settings
from .vboxmanage import VBoxError, run, run_process, validate_vm

# VBoxManage desplaza los códigos de salida del guest: 1..93 -> 33..125,
# >=94 -> 126, y reserva 16..22 para estados propios de VBoxManage.
_GUEST_MAPPED_FIRST = 33
_GUEST_MAPPED_LAST = 125
_GUEST_MAPPED_BIG = 126
_GUEST_MAPPED_DISPLACEMENT = 32

_HINTS = (
    (
        "guest execution service",
        "Guest Additions no están instaladas o su servicio no está en ejecución en la VM. "
        "Instala las Guest Additions e inténtalo de nuevo.",
    ),
    (
        "guest additions",
        "Guest Additions no están disponibles en la VM. Instálalas para usar guestcontrol.",
    ),
    (
        "invalid user name or password",
        "Credenciales del guest incorrectas: revisa usuario y contraseña.",
    ),
    (
        "authentication",
        "Credenciales del guest rechazadas: revisa usuario y contraseña.",
    ),
)


@contextmanager
def password_file(password: str) -> Iterator[str]:
    fd, path = tempfile.mkstemp(prefix="vbox-mcp-", suffix=".pw")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(password)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        yield path
    finally:
        try:
            os.unlink(path)
        except OSError:
            pass


def _translate_error(result) -> None:
    text = f"{result.stdout}\n{result.stderr}".lower()
    for marker, message in _HINTS:
        if marker in text:
            raise VBoxError(message, returncode=result.returncode, stderr=result.stderr)


def guest_exec(
    settings: Settings,
    vm: str,
    user: str,
    password: str,
    exe: str,
    args: list[str] | None = None,
    timeout: int = 60,
    env: dict[str, str] | None = None,
    working_dir: str | None = None,
) -> dict[str, object]:
    vm = validate_vm(vm)
    args = list(args or [])
    env = dict(env or {})
    timeout = max(1, int(timeout))

    with password_file(password) as pwfile:
        command = [
            "guestcontrol",
            vm,
            "run",
            "--exe",
            exe,
            "--username",
            user,
            "--passwordfile",
            pwfile,
            "--wait-stdout",
            "--wait-stderr",
            "--timeout",
            str(int(timeout * 1000)),
        ]
        if working_dir:
            command += ["--cwd", working_dir]
        for key, value in env.items():
            command += ["--putenv", f"{key}={value}"]
        command += ["--", *args]

        result = run_process(command, timeout=timeout + 15, settings=settings)

    if result.returncode == 0:
        exit_code = 0
        note: str | None = None
    elif _GUEST_MAPPED_FIRST <= result.returncode <= _GUEST_MAPPED_LAST:
        exit_code = result.returncode - _GUEST_MAPPED_DISPLACEMENT
        note = None
    elif result.returncode == _GUEST_MAPPED_BIG:
        exit_code = _GUEST_MAPPED_BIG
        note = (
            "El guest terminó con un código >= 94; VBoxManage lo representa como 126."
        )
    else:
        _translate_error(result)
        if result.returncode == 20:
            message = (
                "VBoxManage agotó el tiempo de espera del proceso del guest (código 20)."
            )
        elif result.returncode in {18, 19}:
            message = (
                "El proceso del guest terminó de forma anormal (código "
                f"{result.returncode})."
            )
        else:
            detail = result.stderr.strip() or result.stdout.strip() or "sin detalle"
            message = (
                f"VBoxManage guestcontrol falló con código {result.returncode}: {detail}"
            )
        raise VBoxError(
            message, returncode=result.returncode, stderr=result.stderr
        )

    payload: dict[str, object] = {
        "exit_code": exit_code,
        "stdout": result.stdout,
        "stderr": result.stderr,
    }
    if note:
        payload["note"] = note
    return payload


def guest_copy_to(
    settings: Settings,
    vm: str,
    user: str,
    password: str,
    host_path: str,
    guest_path: str,
    recursive: bool = False,
    timeout: int | None = None,
) -> dict[str, object]:
    vm = validate_vm(vm)
    source = Path(host_path)
    if not source.exists():
        raise VBoxError(f"No existe host_path: {host_path}")

    with password_file(password) as pwfile:
        command = [
            "guestcontrol",
            vm,
            "copyto",
            str(source),
            guest_path,
            "--username",
            user,
            "--passwordfile",
            pwfile,
        ]
        if recursive:
            command.append("--recursive")
        run(command, settings=settings, timeout=timeout)

    return {"vm": vm, "action": "guest_copy_to", "host_path": str(source), "guest_path": guest_path}


def guest_copy_from(
    settings: Settings,
    vm: str,
    user: str,
    password: str,
    guest_path: str,
    host_path: str,
    recursive: bool = False,
    timeout: int | None = None,
) -> dict[str, object]:
    vm = validate_vm(vm)
    target = Path(host_path)
    target.parent.mkdir(parents=True, exist_ok=True)

    with password_file(password) as pwfile:
        command = [
            "guestcontrol",
            vm,
            "copyfrom",
            guest_path,
            str(target),
            "--username",
            user,
            "--passwordfile",
            pwfile,
        ]
        if recursive:
            command.append("--recursive")
        run(command, settings=settings, timeout=timeout)

    return {"vm": vm, "action": "guest_copy_from", "guest_path": guest_path, "host_path": str(target)}
