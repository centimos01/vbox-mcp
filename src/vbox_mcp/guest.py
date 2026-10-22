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
    stdin: str | None = None,
) -> dict[str, object]:
    vm = validate_vm(vm, settings)
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
        if stdin is not None:
            command += ["--stdin", stdin]
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
        exit_code = None
        note = (
            "El guest terminó con un código >= 94; VBoxManage solo informa 126, "
            "así que no se conoce el código exacto."
        )
    else:
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
            _translate_error(result)
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
    vm = validate_vm(vm, settings)
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
    vm = validate_vm(vm, settings)
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

    return {
        "vm": vm,
        "action": "guest_copy_from",
        "guest_path": guest_path,
        "host_path": str(target),
    }


def guest_run_script(
    settings: Settings,
    vm: str,
    user: str,
    password: str,
    script_content: str,
    interpreter: str = "/bin/sh",
    timeout: int = 60,
    env: dict[str, str] | None = None,
    working_dir: str | None = None,
) -> dict[str, object]:
    """Escribe un script en un archivo temporal del host, lo copia al guest y lo ejecuta.

    Útil para ejecutar bloques de código sin tener que escapar cada argumento.
    El archivo temporal del guest se limpia automáticamente tras la ejecución.
    """
    import tempfile

    vm = validate_vm(vm, settings)
    timeout = max(1, int(timeout))

    # Escribe el script en un archivo temporal del host
    fd, host_script = tempfile.mkstemp(prefix="vbox-mcp-script-", suffix=".sh")
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(script_content)

        # Ruta en el guest
        guest_script = f"/tmp/vbox-mcp-script-{id(host_script)}.sh"

        # Copia al guest
        guest_copy_to(
            settings, vm, user, password, host_script, guest_script, timeout=timeout
        )
    finally:
        try:
            os.unlink(host_script)
        except OSError:
            pass

    # Ejecuta en el guest
    try:
        result = guest_exec(
            settings,
            vm,
            user,
            password,
            interpreter,
            args=[guest_script],
            timeout=timeout,
            env=env,
            working_dir=working_dir,
        )
    finally:
        # Limpia el script del guest (best effort)
        try:
            guest_exec(
                settings,
                vm,
                user,
                password,
                "/bin/rm",
                args=["-f", guest_script],
                timeout=15,
            )
        except Exception:
            pass

    result["action"] = "guest_run_script"
    result["interpreter"] = interpreter
    return result

