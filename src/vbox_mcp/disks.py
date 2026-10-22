"""Gestión de discos y medios VirtualBox."""

from __future__ import annotations

from pathlib import Path

from .config import Settings
from .parsing import parse_machine_readable, parse_blocks
from .vboxmanage import VBoxError, run, run_process, validate_vm

_DISK_FORMATS = {"VDI", "VMDK", "VHD"}
_DISK_VARIANTS = {"Standard", "Fixed", "Split2G", "Stream", "ESX"}
_CONTROLLER_TYPES = {"sata", "ide", "scsi", "nvme", "usb", "pcie"}
_DEVICE_TYPES = {"hdd", "dvddrive", "floppy"}


def disk_create(
    settings: Settings,
    path: str,
    size_mb: int,
    fmt: str = "VDI",
    variant: str = "Standard",
) -> dict[str, object]:
    """Crea un nuevo disco virtual independiente."""
    fmt = fmt.upper()
    if fmt not in _DISK_FORMATS:
        raise VBoxError(f"format debe ser uno de {sorted(_DISK_FORMATS)}, no {fmt!r}")
    variant = variant.capitalize()
    if variant not in _DISK_VARIANTS:
        raise VBoxError(f"variant debe ser uno de {sorted(_DISK_VARIANTS)}, no {variant!r}")
    if size_mb < 1:
        raise VBoxError("size_mb debe ser >= 1")

    disk = Path(path)
    if not disk.suffix:
        disk = disk.with_suffix(f".{fmt.lower()}")

    run(
        [
            "createmedium",
            "disk",
            "--filename",
            str(disk),
            "--size",
            str(size_mb),
            "--format",
            fmt,
            "--variant",
            variant,
        ],
        settings=settings,
    )
    return {"action": "disk_create", "path": str(disk), "size_mb": size_mb, "format": fmt}


def disk_attach(
    settings: Settings,
    vm: str,
    disk_path: str,
    controller: str = "sata",
    port: int = 0,
    device: int = 0,
    disk_type: str = "hdd",
    hot_plug: bool = False,
) -> dict[str, object]:
    """Adjunta un disco existente a una VM."""
    vm = validate_vm(vm, settings)
    controller = controller.lower()
    if controller not in _CONTROLLER_TYPES:
        raise VBoxError(f"controller debe ser uno de {sorted(_CONTROLLER_TYPES)}, no {controller!r}")
    disk_type = disk_type.lower()
    if disk_type not in _DEVICE_TYPES:
        raise VBoxError(f"disk_type debe ser uno de {sorted(_DEVICE_TYPES)}, no {disk_type!r}")
    disk = Path(disk_path)
    if not disk.exists():
        raise VBoxError(f"No existe el disco: {disk_path}")

    args = [
        "storageattach",
        vm,
        "--storagectl",
        controller,
        "--port",
        str(port),
        "--device",
        str(device),
        "--type",
        disk_type,
        "--medium",
        str(disk),
    ]
    if hot_plug:
        args += ["--hotpluggable", "on"]
    run(args, settings=settings)
    return {
        "vm": vm,
        "action": "disk_attach",
        "disk": str(disk),
        "controller": controller,
        "port": port,
        "device": device,
    }


def disk_detach(
    settings: Settings,
    vm: str,
    controller: str = "sata",
    port: int = 0,
    device: int = 0,
) -> dict[str, object]:
    """Desadjunta un disco de una VM (no lo borra)."""
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
            str(device),
            "--medium",
            "none",
        ],
        settings=settings,
    )
    return {
        "vm": vm,
        "action": "disk_detach",
        "controller": controller,
        "port": port,
        "device": device,
    }


def disk_resize(
    settings: Settings,
    disk_path: str,
    new_size_mb: int,
) -> dict[str, object]:
    """Redimensiona un disco VDI (solo se puede ampliar, no reducir)."""
    if new_size_mb < 1:
        raise VBoxError("new_size_mb debe ser >= 1")
    disk = Path(disk_path)
    if not disk.exists():
        raise VBoxError(f"No existe el disco: {disk_path}")
    run(
        ["modifymedium", "disk", str(disk), "--resize", str(new_size_mb)],
        settings=settings,
    )
    return {"action": "disk_resize", "path": str(disk), "new_size_mb": new_size_mb}


def disk_info(settings: Settings, disk_path: str) -> dict[str, object]:
    """Obtiene información de un medio (disco/ISO) registrado en VirtualBox."""
    result = run_process(
        ["showmediuminfo", "disk", disk_path],
        settings=settings,
    )
    if result.returncode != 0:
        # Intentar como dvd
        result2 = run_process(
            ["showmediuminfo", "dvd", disk_path],
            settings=settings,
        )
        if result2.returncode != 0:
            detail = result.stderr.strip() or result.stdout.strip() or "sin detalle"
            raise VBoxError(f"No se pudo obtener info del medio: {detail}")
        text = result2.stdout
    else:
        text = result.stdout

    info: dict[str, str] = {}
    for line in text.splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            info[key.strip().lower().replace(" ", "_")] = value.strip()
    return {"path": disk_path, "info": info}


def list_media(settings: Settings, media_type: str = "disk") -> dict[str, object]:
    """Lista todos los medios registrados en VirtualBox."""
    valid_types = {"disk", "dvd", "floppy"}
    media_type = media_type.lower()
    if media_type not in valid_types:
        raise VBoxError(f"media_type debe ser uno de {sorted(valid_types)}, no {media_type!r}")

    cmd_map = {"disk": "hdds", "dvd": "dvds", "floppy": "floppies"}
    result = run_process(
        ["list", "--long", cmd_map[media_type]],
        settings=settings,
    )
    if result.returncode != 0:
        raise VBoxError(
            f"No se pudo listar medios: {result.stderr.strip() or result.stdout.strip()}"
        )

    media: list[dict[str, str]] = []
    for block in result.stdout.strip().split("\n\n"):
        block = block.strip()
        if not block:
            continue
        entry: dict[str, str] = {}
        for line in block.splitlines():
            if ":" in line:
                key, _, value = line.partition(":")
                entry[key.strip().lower().replace(" ", "_")] = value.strip()
        if entry:
            media.append(entry)

    return {"type": media_type, "media": media, "count": len(media)}
