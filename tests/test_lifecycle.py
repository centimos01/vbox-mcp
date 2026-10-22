from __future__ import annotations

import pytest

from vbox_mcp.config import Settings
from vbox_mcp.lifecycle import (
    clone_vm,
    create_vm,
    delete_vm,
    modify_vm,
    pause_vm,
    reset_vm,
    resume_vm,
    start_vm,
    stop_vm,
)
from vbox_mcp.vboxmanage import VBoxError


def test_start_vm_headless(settings: Settings, fake) -> None:
    result = start_vm(settings, "Win10", mode="headless")

    assert fake.last_args == ["startvm", "Win10", "--type", "headless"]
    assert result == {"vm": "Win10", "action": "start", "mode": "headless"}


def test_start_vm_gui(settings: Settings, fake) -> None:
    start_vm(settings, "Win10", mode="gui")

    assert fake.last_args == ["startvm", "Win10", "--type", "gui"]


def test_start_vm_rejects_bad_mode(settings: Settings) -> None:
    with pytest.raises(VBoxError, match="mode"):
        start_vm(settings, "Win10", mode="detached")


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("acpi", ["controlvm", "Win10", "acpipowerbutton"]),
        ("poweroff", ["controlvm", "Win10", "poweroff"]),
        ("save", ["controlvm", "Win10", "savestate"]),
    ],
)
def test_stop_vm_modes(settings: Settings, fake, mode: str, expected: list[str]) -> None:
    stop_vm(settings, "Win10", mode=mode)

    assert fake.last_args == expected


def test_pause_resume_reset(settings: Settings, fake) -> None:
    pause_vm(settings, "Win10")
    assert fake.last_args == ["controlvm", "Win10", "pause"]

    resume_vm(settings, "Win10")
    assert fake.last_args == ["controlvm", "Win10", "resume"]

    reset_vm(settings, "Win10")
    assert fake.last_args == ["controlvm", "Win10", "reset"]


def test_create_vm_minimal(settings: Settings, fake) -> None:
    result = create_vm(settings, "NewVM", "Windows10_64", cpus=4, memory_mb=8192)

    assert fake.calls() == [
        ["createvm", "--name", "NewVM", "--ostype", "Windows10_64", "--register"],
        ["modifyvm", "NewVM", "--cpus", "4", "--memory", "8192", "--nic1", "nat"],
    ]
    assert result["name"] == "NewVM"
    assert result["disk"] is None


def test_create_vm_with_disk(settings: Settings, fake) -> None:
    fake.response(
        "showvminfo NewVM --machinereadable",
        stdout='CfgFile="C:\\\\VMs\\\\NewVM\\\\NewVM.vbox"\n',
    )

    create_vm(settings, "NewVM", "Windows10_64", disk_mb=10240)

    calls = fake.calls()
    assert ["createmedium", "disk", "--filename", r"C:\VMs\NewVM\NewVM.vdi", "--size", "10240", "--format", "VDI"] in calls
    assert ["storagectl", "NewVM", "--name", "sata", "--add", "sata", "--controller", "IntelAhci"] in calls
    assert [
        "storageattach",
        "NewVM",
        "--storagectl",
        "sata",
        "--port",
        "0",
        "--device",
        "0",
        "--type",
        "hdd",
        "--medium",
        r"C:\VMs\NewVM\NewVM.vdi",
    ] in calls


def test_create_vm_attaches_iso(settings: Settings, fake, tmp_path) -> None:
    iso = tmp_path / "install.iso"
    iso.write_bytes(b"iso")

    create_vm(settings, "NewVM", "Ubuntu24_LTS_64", iso=str(iso))

    assert fake.last_args == [
        "storageattach",
        "NewVM",
        "--storagectl",
        "sata",
        "--port",
        "1",
        "--device",
        "0",
        "--type",
        "dvddrive",
        "--medium",
        str(iso),
    ]


def test_modify_vm_requires_a_change(settings: Settings) -> None:
    with pytest.raises(VBoxError, match="al menos"):
        modify_vm(settings, "Win10")


def test_modify_vm_args(settings: Settings, fake) -> None:
    modify_vm(
        settings, "Win10", cpus=8, memory_mb=16384, nic="bridged", adapter="Ethernet"
    )

    assert fake.last_args == [
        "modifyvm",
        "Win10",
        "--cpus",
        "8",
        "--memory",
        "16384",
        "--nic1",
        "bridged",
        "--bridgeadapter1",
        "Ethernet",
    ]


def test_clone_vm_full(settings: Settings, fake) -> None:
    clone_vm(settings, "Win10", "Win10-copia")

    assert fake.last_args == [
        "clonevm",
        "Win10",
        "--name",
        "Win10-copia",
        "--register",
        "--mode",
        "machine",
    ]


def test_clone_vm_linked_from_snapshot(settings: Settings, fake) -> None:
    clone_vm(settings, "Win10", "Win10-test", mode="linked", snapshot="base")

    assert fake.last_args == [
        "clonevm",
        "Win10",
        "--name",
        "Win10-test",
        "--register",
        "--mode",
        "machine",
        "--options",
        "link",
        "--snapshot",
        "base",
    ]


def test_delete_vm_keeps_disks_by_default(settings: Settings, fake) -> None:
    delete_vm(settings, "Win10")

    assert fake.last_args == ["unregistervm", "Win10"]


def test_delete_vm_can_delete_disks(settings: Settings, fake) -> None:
    delete_vm(settings, "Win10", delete_disks=True)

    assert fake.last_args == ["unregistervm", "Win10", "--delete"]


def test_create_vm_bridged_requires_adapter(settings: Settings) -> None:
    with pytest.raises(VBoxError, match="adapter"):
        create_vm(settings, "NewVM", "Windows10_64", network="bridged")


def test_create_vm_bridged_with_adapter(settings: Settings, fake) -> None:
    create_vm(settings, "NewVM", "Windows10_64", network="bridged", adapter="Ethernet")

    assert fake.last_args == [
        "modifyvm",
        "NewVM",
        "--cpus",
        "2",
        "--memory",
        "2048",
        "--nic1",
        "bridged",
        "--bridgeadapter1",
        "Ethernet",
    ]


def test_modify_vm_bridged_requires_adapter(settings: Settings) -> None:
    with pytest.raises(VBoxError, match="adapter"):
        modify_vm(settings, "Win10", nic="bridged")
