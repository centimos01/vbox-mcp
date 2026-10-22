from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

from vbox_mcp import vboxmanage
from vbox_mcp.config import Settings
from vbox_mcp.vboxmanage import (
    VBoxError,
    guest_ip,
    list_networks,
    list_ostypes,
    list_vms,
    parse_blocks,
    run,
    run_process,
    snapshot_list,
    validate_vm,
    vm_info,
)

UUID1 = "11111111-1111-1111-1111-111111111111"
UUID2 = "22222222-2222-2222-2222-222222222222"


def test_run_invokes_fake_and_returns_stdout(settings: Settings, fake) -> None:
    fake.response("list vms", stdout='"Win10" {' + UUID1 + '}\n')

    out = run(["list", "vms"], settings=settings)

    assert out == '"Win10" {' + UUID1 + '}\n'
    assert fake.last_args == ["list", "vms"]


def test_run_raises_with_stderr(settings: Settings, fake) -> None:
    fake.response("list vms", stderr="VBoxManage: error: boom", returncode=1)

    with pytest.raises(VBoxError) as exc:
        run(["list", "vms"], settings=settings)

    assert "boom" in str(exc.value)
    assert exc.value.returncode == 1


def test_run_without_vboxmanage_raises(tmp_path: Path) -> None:
    settings = Settings(
        vboxmanage_path=None,
        readonly=False,
        timeout_seconds=60,
        audit_log=tmp_path / "audit.log",
        allow_mouse=True,
        guest_user=None,
        guest_password=None,
    )

    with pytest.raises(VBoxError, match="VBoxManage"):
        run(["list", "vms"], settings=settings)


def test_run_process_returns_stderr_and_code(settings: Settings, fake) -> None:
    fake.response("controlvm x poweroff", stderr="nope", returncode=2)

    result = run_process(["controlvm", "x", "poweroff"], settings=settings)

    assert result.returncode == 2
    assert result.stderr == "nope"


def test_run_timeout(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*args, **kwargs):
        raise subprocess.TimeoutExpired(cmd="VBoxManage", timeout=1)

    monkeypatch.setattr(vboxmanage.subprocess, "run", boom)

    with pytest.raises(VBoxError, match="timeout"):
        run(["list", "vms"], settings=settings, timeout=1)


def test_list_vms_merges_running_state(settings: Settings, fake) -> None:
    fake.response("list vms", stdout=f'"Win10" {{{UUID1}}}\n"Ubuntu" {{{UUID2}}}\n')
    fake.response("list runningvms", stdout=f'"Win10" {{{UUID1}}}\n')

    vms = list_vms(settings)

    assert vms == [
        {"name": "Win10", "uuid": UUID1, "state": "running"},
        {"name": "Ubuntu", "uuid": UUID2, "state": "stopped"},
    ]


def test_list_vms_running_only(settings: Settings, fake) -> None:
    fake.response("list runningvms", stdout=f'"Win10" {{{UUID1}}}\n')

    assert list_vms(settings, running_only=True) == [
        {"name": "Win10", "uuid": UUID1, "state": "running"}
    ]


def test_vm_info_summary(settings: Settings, fake) -> None:
    fake.response(
        "showvminfo Win10 --machinereadable",
        stdout=(
            'name="Win10"\n'
            f'UUID="{UUID1}"\n'
            'VMState="poweroff"\n'
            "cpus=4\n"
            "memory=4096\n"
            'ostype="Windows10_64"\n'
            'GuestAdditionsVersion="7.2.20"\n'
        ),
    )

    info = vm_info(settings, "Win10")

    assert info["summary"] == {
        "name": "Win10",
        "uuid": UUID1,
        "state": "poweroff",
        "cpus": 4,
        "memory_mb": 4096,
        "ostype": "Windows10_64",
        "guest_additions": "7.2.20",
    }
    assert info["raw"]["memory"] == "4096"


def test_list_ostypes(settings: Settings, fake) -> None:
    fake.response(
        "list ostypes",
        stdout="ID:          Windows10_64\nDescription: Windows 10 (64-bit)\nFamily ID: Windows\nFamily Desc: Microsoft Windows\n64 bit: true\n",
    )

    assert list_ostypes(settings)[0]["id"] == "Windows10_64"


def test_snapshot_list(settings: Settings, fake) -> None:
    fake.response(
        "snapshot Win10 list --machinereadable",
        stdout='CurrentSnapshotName="a"\nSnapshotName="a"\nSnapshotUUID="' + UUID1 + '"\nSnapshotDescription=""\n',
    )

    assert snapshot_list(settings, "Win10")[0]["current"] is True


def test_list_networks(settings: Settings, fake) -> None:
    fake.response("list hostonlyifs --machinereadable", stdout='NetworkName="HostOnly"\nIPAddress="192.168.56.1"\n')
    fake.response("list natnets --machinereadable", stdout='NetworkName="NatNet"\n')

    assert list_networks(settings) == {
        "hostonly": [{"NetworkName": "HostOnly", "IPAddress": "192.168.56.1"}],
        "natnets": [{"NetworkName": "NatNet"}],
    }


def test_guest_ip(settings: Settings, fake) -> None:
    fake.response(
        "guestproperty get Win10 /VirtualBox/GuestInfo/Net/0/V4/IP",
        stdout="Value: 10.0.2.15\n",
    )

    assert guest_ip(settings, "Win10") == "10.0.2.15"


def test_guest_ip_none_when_unset(settings: Settings, fake) -> None:
    fake.response(
        "guestproperty get Win10 /VirtualBox/GuestInfo/Net/0/V4/IP",
        stdout="No value set!\n",
    )

    assert guest_ip(settings, "Win10") is None


def test_validate_vm_rejects_empty_and_flags() -> None:
    for bad in ("", "   ", "-evil", "--foo"):
        with pytest.raises(VBoxError):
            validate_vm(bad)

    assert validate_vm("  Win10 ") == "Win10"
