from __future__ import annotations

from pathlib import Path

import pytest

from vbox_mcp import config
from vbox_mcp.config import Settings, find_vboxmanage


def test_env_var_wins(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = tmp_path / "VBoxManage.exe"
    fake.write_text("")
    monkeypatch.setattr(config, "STANDARD_PATHS", [])

    settings = Settings.from_env({"VBOX_MANAGE_PATH": str(fake)})

    assert settings.vboxmanage_path == fake


def test_env_var_is_used_even_if_missing(tmp_path: Path) -> None:
    missing = tmp_path / "nope" / "VBoxManage.exe"

    settings = Settings.from_env({"VBOX_MANAGE_PATH": str(missing)})

    assert settings.vboxmanage_path == missing


def test_readonly_parsing() -> None:
    for value in ("true", "1", "yes", "on", "TRUE"):
        assert Settings.from_env({"VBOX_MCP_READONLY": value}).readonly is True
    for value in ("false", "0", "no", "off", ""):
        assert Settings.from_env({"VBOX_MCP_READONLY": value}).readonly is False


def test_defaults() -> None:
    settings = Settings.from_env({})

    assert settings.timeout_seconds == 60
    assert settings.allow_mouse is True
    assert settings.guest_user is None
    assert settings.guest_password is None
    assert settings.audit_log.name == "audit.log"


def test_custom_timeout_and_audit_path(tmp_path: Path) -> None:
    audit = tmp_path / "audit.jsonl"

    settings = Settings.from_env(
        {
            "VBOX_MCP_TIMEOUT_SECONDS": "15",
            "VBOX_MCP_AUDIT_LOG": str(audit),
            "VBOX_MCP_ALLOW_MOUSE": "false",
        }
    )

    assert settings.timeout_seconds == 15
    assert settings.audit_log == audit
    assert settings.allow_mouse is False


def test_find_vboxmanage_uses_path_lookup(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = tmp_path / "VBoxManage"
    fake.write_text("")
    monkeypatch.setattr(config, "STANDARD_PATHS", [])
    monkeypatch.setattr(config.shutil, "which", lambda name: str(fake) if name == "VBoxManage" else None)

    assert find_vboxmanage({}) == fake


def test_find_vboxmanage_uses_standard_path(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = tmp_path / "VBoxManage.exe"
    fake.write_text("")
    monkeypatch.setattr(config, "STANDARD_PATHS", [fake])
    monkeypatch.setattr(config.shutil, "which", lambda name: None)

    assert find_vboxmanage({}) == fake


def test_find_vboxmanage_returns_none(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(config, "STANDARD_PATHS", [tmp_path / "missing"])
    monkeypatch.setattr(config.shutil, "which", lambda name: None)

    assert find_vboxmanage({}) is None
