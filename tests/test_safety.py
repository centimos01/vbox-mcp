from __future__ import annotations

import json
from pathlib import Path

import pytest

from vbox_mcp.config import Settings
from vbox_mcp.safety import (
    ConfirmationRequired,
    audit,
    ensure_writable,
    redact,
    require_confirm,
)
from vbox_mcp.vboxmanage import VBoxError


def make_settings(tmp_path: Path, readonly: bool = False) -> Settings:
    return Settings(
        vboxmanage_path=tmp_path / "VBoxManage.exe",
        readonly=readonly,
        timeout_seconds=60,
        audit_log=tmp_path / "nested" / "audit.log",
        allow_mouse=True,
        guest_user=None,
        guest_password=None,
    )


def test_ensure_writable_blocks_readonly(tmp_path: Path) -> None:
    with pytest.raises(VBoxError, match="solo lectura"):
        ensure_writable(make_settings(tmp_path, readonly=True))


def test_ensure_writable_allows_normal_mode(tmp_path: Path) -> None:
    ensure_writable(make_settings(tmp_path))


def test_require_confirm_raises_with_effects(tmp_path: Path) -> None:
    with pytest.raises(ConfirmationRequired) as exc:
        require_confirm(False, "poweroff", "Win10", ["se perderá el estado no guardado"])

    assert exc.value.action == "poweroff"
    assert exc.value.target == "Win10"
    assert exc.value.effects == ["se perderá el estado no guardado"]


def test_require_confirm_passes_when_confirmed() -> None:
    require_confirm(True, "poweroff", "Win10", [])


def test_redact_masks_nested_secrets() -> None:
    payload = {
        "vm": "Win10",
        "password": "hunter2",
        "nested": {"PASSWORD": "x", "token": "y", "ok": 1},
        "items": [{"secret": "z", "name": "a"}],
    }

    redacted = redact(payload)

    assert redacted["password"] == "***"
    assert redacted["nested"]["PASSWORD"] == "***"
    assert redacted["nested"]["token"] == "***"
    assert redacted["items"][0]["secret"] == "***"
    assert redacted["nested"]["ok"] == 1
    assert redacted["vm"] == "Win10"


def test_audit_writes_jsonl_and_redacts(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)

    audit(settings, "vbox_create_vm", {"name": "x", "password": "hunter2"}, "ok", 12)

    lines = settings.audit_log.read_text(encoding="utf-8").splitlines()
    entry = json.loads(lines[0])
    assert entry["tool"] == "vbox_create_vm"
    assert entry["args"]["password"] == "***"
    assert entry["result"] == "ok"
    assert entry["duration_ms"] == 12
    assert "ts" in entry
    assert "hunter2" not in settings.audit_log.read_text(encoding="utf-8")


def test_audit_never_breaks_the_call_on_io_error(tmp_path: Path) -> None:
    settings = make_settings(tmp_path)
    settings.audit_log.parent.mkdir(parents=True, exist_ok=True)
    settings.audit_log.write_text("not a dir")
    settings.audit_log.chmod(0o444)

    audit(settings, "tool", {}, "ok", 1)
