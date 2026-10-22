"""Exportación e importación de VMs (OVA/OVF)."""

from __future__ import annotations

from pathlib import Path

from .config import Settings
from .vboxmanage import VBoxError, run, run_process, validate_vm

_EXPORT_FORMATS = {"ovf09", "ovf10", "ovf20", "ova"}


def export_vm(
    settings: Settings,
    vm: str,
    output: str,
    fmt: str = "ova",
    manifest: bool = True,
    description: str = "",
    timeout: int | None = None,
) -> dict[str, object]:
    """Exporta una VM a un archivo OVA u OVF."""
    vm = validate_vm(vm, settings)
    fmt = fmt.lower()
    if fmt not in _EXPORT_FORMATS:
        raise VBoxError(f"fmt debe ser uno de {sorted(_EXPORT_FORMATS)}, no {fmt!r}")

    out = Path(output)
    out.parent.mkdir(parents=True, exist_ok=True)

    args = [
        "export",
        vm,
        "--output",
        str(out),
        "--ovf20" if fmt == "ovf20" else f"--{fmt}",
    ]
    if not manifest:
        args.append("--no-manifest")
    if description:
        args += ["--vsys", "0", "--description", description]

    run(args, settings=settings, timeout=timeout)
    return {
        "vm": vm,
        "action": "export",
        "output": str(out),
        "format": fmt,
    }


def import_vm(
    settings: Settings,
    path: str,
    name: str = "",
    base_folder: str = "",
    cpus: int | None = None,
    memory_mb: int | None = None,
    timeout: int | None = None,
) -> dict[str, object]:
    """Importa una VM desde un archivo OVA u OVF."""
    src = Path(path)
    if not src.exists():
        raise VBoxError(f"No existe el archivo: {path}")

    args = ["import", str(src)]
    if name:
        args += ["--vsys", "0", "--vmname", name]
    if base_folder:
        args += ["--vsys", "0", "--basefolder", base_folder]
    if cpus is not None:
        args += ["--vsys", "0", "--cpus", str(cpus)]
    if memory_mb is not None:
        args += ["--vsys", "0", "--memory", str(memory_mb)]

    run(args, settings=settings, timeout=timeout)
    return {
        "action": "import",
        "source": str(src),
        "name": name or "(auto)",
    }
