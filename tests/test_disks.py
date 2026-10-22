from __future__ import annotations

import pytest

from vbox_mcp.config import Settings
from vbox_mcp.disks import (
    disk_attach,
    disk_create,
    disk_detach,
    disk_info,
    disk_resize,
    list_media,
)
from vbox_mcp.vboxmanage import VBoxError


def test_disk_create_vdi(settings: Settings, fake) -> None:
    result = disk_create(settings, "test.vdi", 1024, fmt="VDI", variant="Standard")

    assert fake.last_args == [
        "createmedium",
        "disk",
        "--filename",
        "test.vdi",
        "--size",
        "1024",
        "--format",
        "VDI",
        "--variant",
        "Standard",
    ]
    assert result == {"action": "disk_create", "path": "test.vdi", "size_mb": 1024, "format": "VDI"}


def test_disk_create_adds_extension(settings: Settings, fake) -> None:
    disk_create(settings, "test", 1024, fmt="VMDK")

    assert fake.last_args[3] == "test.vmdk"


def test_disk_create_rejects_bad_format(settings: Settings) -> None:
    with pytest.raises(VBoxError, match="format"):
        disk_create(settings, "test.vdi", 1024, fmt="RAW")


def test_disk_create_rejects_bad_variant(settings: Settings) -> None:
    with pytest.raises(VBoxError, match="variant"):
        disk_create(settings, "test.vdi", 1024, variant="Weird")


def test_disk_create_rejects_zero_size(settings: Settings) -> None:
    with pytest.raises(VBoxError, match="size_mb"):
        disk_create(settings, "test.vdi", 0)


def test_disk_attach(settings: Settings, fake, tmp_path) -> None:
    disk = tmp_path / "disk.vdi"
    disk.write_bytes(b"data")

    disk_attach(settings, "Win10", str(disk), controller="sata", port=0, device=0, disk_type="hdd")

    assert fake.last_args[:8] == ["storageattach", "Win10", "--storagectl", "sata", "--port", "0", "--device", "0"]


def test_disk_attach_rejects_missing_disk(settings: Settings, tmp_path) -> None:
    with pytest.raises(VBoxError, match="No existe el disco"):
        disk_attach(settings, "Win10", str(tmp_path / "missing.vdi"))


def test_disk_attach_rejects_bad_controller(settings: Settings, tmp_path) -> None:
    disk = tmp_path / "disk.vdi"
    disk.write_bytes(b"data")

    with pytest.raises(VBoxError, match="controller"):
        disk_attach(settings, "Win10", str(disk), controller="floppy")


def test_disk_detach(settings: Settings, fake) -> None:
    disk_detach(settings, "Win10", controller="sata", port=0, device=0)

    assert fake.last_args == [
        "storageattach",
        "Win10",
        "--storagectl",
        "sata",
        "--port",
        "0",
        "--device",
        "0",
        "--medium",
        "none",
    ]


def test_disk_resize(settings: Settings, fake, tmp_path) -> None:
    disk = tmp_path / "disk.vdi"
    disk.write_bytes(b"data")

    result = disk_resize(settings, str(disk), 2048)

    assert fake.last_args == ["modifymedium", "disk", str(disk), "--resize", "2048"]
    assert result == {"action": "disk_resize", "path": str(disk), "new_size_mb": 2048}


def test_disk_resize_rejects_missing_disk(settings: Settings, tmp_path) -> None:
    with pytest.raises(VBoxError, match="No existe el disco"):
        disk_resize(settings, str(tmp_path / "missing.vdi"), 2048)


def test_disk_info(settings: Settings, fake) -> None:
    fake.response(
        "showmediuminfo disk test.vdi",
        stdout="UUID: 12345678-1234-1234-1234-123456789012\nSize: 10737418240\nFormat: VDI\nState: created\n",
    )

    result = disk_info(settings, "test.vdi")

    assert result["path"] == "test.vdi"
    assert "uuid" in result["info"]


def test_disk_info_tries_dvd_on_disk_failure(settings: Settings, fake) -> None:
    fake.response("showmediuminfo disk test.iso", returncode=1, stderr="not found")
    fake.response(
        "showmediuminfo dvd test.iso",
        stdout="UUID: 87654321-4321-4321-4321-210987654321\nSize: 536870912\nFormat: ISO\nState: created\n",
    )

    result = disk_info(settings, "test.iso")

    assert result["path"] == "test.iso"


def test_list_media_disks(settings: Settings, fake) -> None:
    fake.response(
        "list --long hdds",
        stdout='UUID: 11111111-1111-1111-1111-111111111111\nLocation: C:\\VMs\\disk1.vdi\nFormat: VDI\nSize: 10737418240\n\nUUID: 22222222-2222-2222-2222-222222222222\nLocation: C:\\VMs\\disk2.vdi\nFormat: VMDK\nSize: 21474836480\n',
    )

    result = list_media(settings, "disk")

    assert result["type"] == "disk"
    assert result["count"] == 2
    assert result["media"][0]["uuid"] == "11111111-1111-1111-1111-111111111111"


def test_list_media_dvds(settings: Settings, fake) -> None:
    fake.response("list --long dvds", stdout='UUID: 11111111-1111-1111-1111-111111111111\nLocation: C:\\ISOs\\ubuntu.iso\n')

    result = list_media(settings, "dvd")

    assert result["type"] == "dvd"
    assert result["count"] == 1


def test_list_media_floppies(settings: Settings, fake) -> None:
    fake.response("list --long floppies", stdout='UUID: 11111111-1111-1111-1111-111111111111\nLocation: C:\\floppy.img\n')

    result = list_media(settings, "floppy")

    assert result["type"] == "floppy"
    assert result["count"] == 1


def test_list_media_rejects_bad_type(settings: Settings) -> None:
    with pytest.raises(VBoxError, match="media_type"):
        list_media(settings, "tape")