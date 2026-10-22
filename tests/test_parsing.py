from __future__ import annotations

from vbox_mcp.parsing import (
    parse_blocks,
    parse_machine_readable,
    parse_ostypes,
    parse_snapshots,
    parse_vm_list,
)


def test_parse_vm_list_with_spaces_and_unicode() -> None:
    text = (
        '"Servidor windows del maestro guapo hermiso" {188c484f-c230-4719-8eec-12422af70472}\n'
        '"windows 10" {b55b3040-0458-4052-9313-a0f86e7cf703}\n'
        "\n"
    )

    assert parse_vm_list(text) == [
        {"name": "Servidor windows del maestro guapo hermiso", "uuid": "188c484f-c230-4719-8eec-12422af70472"},
        {"name": "windows 10", "uuid": "b55b3040-0458-4052-9313-a0f86e7cf703"},
    ]


def test_parse_vm_list_ignores_garbage() -> None:
    assert parse_vm_list("noise\n\n") == []


def test_parse_machine_readable() -> None:
    text = (
        'name="Windows 10"\n'
        "memory=2048\n"
        'VMState="poweroff"\n'
        'ostype="Windows10_64"\n'
        'description=""\n'
        'CfgFile="C:\\\\Users\\\\Usuario\\\\VirtualBox VMs\\\\Windows 10\\\\Windows 10.vbox"\n'
    )

    data = parse_machine_readable(text)

    assert data["name"] == "Windows 10"
    assert data["memory"] == "2048"
    assert data["VMState"] == "poweroff"
    assert data["CfgFile"] == r"C:\Users\Usuario\VirtualBox VMs\Windows 10\Windows 10.vbox"


def test_parse_machine_readable_unquotes_escapes() -> None:
    assert parse_machine_readable('key="a \\"b\\" c"\n')["key"] == 'a "b" c'


def test_parse_ostypes() -> None:
    text = (
        "ID:          Windows10_64\n"
        "Description: Windows 10 (64-bit)\n"
        "Family ID:   Windows\n"
        "Family Desc: Microsoft Windows\n"
        "64 bit:      true\n"
        "\n"
        "ID:          Ubuntu24_LTS_64\n"
        "Description: Ubuntu 24.04 LTS (64-bit)\n"
        "Family ID:   Linux\n"
        "Family Desc: Linux\n"
        "64 bit:      true\n"
    )

    ostypes = parse_ostypes(text)

    assert ostypes[0] == {
        "id": "Windows10_64",
        "description": "Windows 10 (64-bit)",
        "family": "Microsoft Windows",
        "bits": "64",
    }
    assert ostypes[1]["id"] == "Ubuntu24_LTS_64"
    assert ostypes[1]["family"] == "Linux"


def test_parse_snapshots_marks_current() -> None:
    text = (
        'CurrentSnapshotName="limpia"\n'
        'SnapshotName="limpia"\n'
        'SnapshotUUID="11111111-1111-1111-1111-111111111111"\n'
        'SnapshotDescription="sin cambios"\n'
        'SnapshotName-1="base"\n'
        'SnapshotUUID-1="22222222-2222-2222-2222-222222222222"\n'
        'SnapshotDescription-1=""\n'
    )

    snapshots = parse_snapshots(text)

    assert snapshots[0] == {
        "name": "limpia",
        "uuid": "11111111-1111-1111-1111-111111111111",
        "description": "sin cambios",
        "current": True,
    }
    assert snapshots[1]["name"] == "base"
    assert snapshots[1]["current"] is False


def test_parse_blocks() -> None:
    text = (
        'NetworkName="HostOnly"\nIPAddress="192.168.56.1"\n'
        "\n"
        'NetworkName="vboxnet1"\nIPAddress="10.0.0.1"\n'
    )

    blocks = parse_blocks(text)

    assert blocks == [
        {"NetworkName": "HostOnly", "IPAddress": "192.168.56.1"},
        {"NetworkName": "vboxnet1", "IPAddress": "10.0.0.1"},
    ]
