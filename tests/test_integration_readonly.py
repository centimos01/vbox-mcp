"""Smoke tests contra VirtualBox real. Solo lectura."""

from __future__ import annotations

import pytest

from vbox_mcp.config import Settings
from vbox_mcp.vboxmanage import list_vms, vm_info

pytestmark = pytest.mark.integration


def test_real_list_vms_and_info() -> None:
    settings = Settings.from_env()
    if settings.vboxmanage_path is None:
        pytest.skip("VirtualBox no está instalado")

    vms = list_vms(settings)
    assert vms, "VirtualBox no tiene VMs registradas"

    info = vm_info(settings, vms[0]["uuid"])
    assert info["summary"]["name"]
