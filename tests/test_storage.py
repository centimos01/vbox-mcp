from __future__ import annotations

import pytest

from vbox_mcp.config import Settings
from vbox_mcp.storage import (
    attach_iso,
    detach_iso,
    nat_port_forward_add,
    nat_port_forward_remove,
    shared_folder_add,
    shared_folder_remove,
)
from vbox_mcp.vboxmanage import VBoxError


def test_attach_iso(settings: Settings, fake, tmp_path) -> None:
    iso = tmp_path / "ubuntu.iso"
    iso.write_bytes(b"iso")

    attach_iso(settings, "Ubuntu", str(iso))

    assert fake.last_args == [
        "storageattach",
        "Ubuntu",
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


def test_attach_iso_requires_existing_file(settings: Settings, tmp_path) -> None:
    with pytest.raises(VBoxError, match="No existe el ISO"):
        attach_iso(settings, "Ubuntu", str(tmp_path / "missing.iso"))


def test_detach_iso(settings: Settings, fake) -> None:
    detach_iso(settings, "Ubuntu")

    assert fake.last_args == [
        "storageattach",
        "Ubuntu",
        "--storagectl",
        "sata",
        "--port",
        "1",
        "--device",
        "0",
        "--type",
        "dvddrive",
        "--medium",
        "none",
    ]


def test_shared_folder_add(settings: Settings, fake, tmp_path) -> None:
    shared_folder_add(settings, "Ubuntu", "proyecto", str(tmp_path), automount=True, readonly=True)

    assert fake.last_args == [
        "sharedfolder",
        "add",
        "Ubuntu",
        "--name",
        "proyecto",
        "--hostpath",
        str(tmp_path),
        "--automount",
        "--readonly",
    ]


def test_shared_folder_add_rejects_missing_host_path(settings: Settings, tmp_path) -> None:
    with pytest.raises(VBoxError, match="host_path"):
        shared_folder_add(settings, "Ubuntu", "x", str(tmp_path / "nope"))


def test_shared_folder_remove(settings: Settings, fake) -> None:
    shared_folder_remove(settings, "Ubuntu", "proyecto")

    assert fake.last_args == ["sharedfolder", "remove", "Ubuntu", "--name", "proyecto"]


def test_nat_port_forward_add(settings: Settings, fake) -> None:
    nat_port_forward_add(
        settings,
        "Ubuntu",
        rule_name="web",
        protocol="tcp",
        host_port=8080,
        guest_port=80,
    )

    assert fake.last_args == ["modifyvm", "Ubuntu", "--natpf1", "web,tcp,,8080,,80"]


def test_nat_port_forward_add_with_guest_ip(settings: Settings, fake) -> None:
    nat_port_forward_add(
        settings,
        "Ubuntu",
        rule_name="ssh",
        protocol="tcp",
        host_port=2222,
        guest_port=22,
        guest_ip="10.0.2.15",
    )

    assert fake.last_args == ["modifyvm", "Ubuntu", "--natpf1", "ssh,tcp,,2222,10.0.2.15,22"]


def test_nat_port_forward_add_rejects_unknown_protocol(settings: Settings) -> None:
    with pytest.raises(VBoxError, match="protocol"):
        nat_port_forward_add(
            settings, "Ubuntu", rule_name="x", protocol="sctp", host_port=1, guest_port=2
        )


def test_nat_port_forward_remove(settings: Settings, fake) -> None:
    nat_port_forward_remove(settings, "Ubuntu", "web")

    assert fake.last_args == ["modifyvm", "Ubuntu", "--natpf1", "delete", "web"]
