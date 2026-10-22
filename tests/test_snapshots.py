from __future__ import annotations

import pytest

from vbox_mcp.config import Settings
from vbox_mcp.snapshots import snapshot_delete, snapshot_restore, snapshot_take
from vbox_mcp.vboxmanage import VBoxError


def test_snapshot_take(settings: Settings, fake) -> None:
    result = snapshot_take(settings, "Win10", "base", "sin cambios")

    assert fake.last_args == ["snapshot", "Win10", "take", "base", "--description", "sin cambios"]
    assert result == {"vm": "Win10", "action": "snapshot_take", "name": "base"}


def test_snapshot_take_without_description(settings: Settings, fake) -> None:
    snapshot_take(settings, "Win10", "base")

    assert fake.last_args == ["snapshot", "Win10", "take", "base"]


def test_snapshot_restore(settings: Settings, fake) -> None:
    snapshot_restore(settings, "Win10", "base")

    assert fake.last_args == ["snapshot", "Win10", "restore", "base"]


def test_snapshot_delete(settings: Settings, fake) -> None:
    snapshot_delete(settings, "Win10", "base")

    assert fake.last_args == ["snapshot", "Win10", "delete", "base"]


@pytest.mark.parametrize("name", ["", "  ", "--help", "-delete"])
def test_snapshot_names_cannot_be_flags(settings: Settings, name: str) -> None:
    with pytest.raises(VBoxError, match="snapshot"):
        snapshot_take(settings, "Win10", name)
