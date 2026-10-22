from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from vbox_mcp.config import Settings

FAKE_SCRIPT = Path(__file__).parent / "fake_vboxmanage.py"


class FakeVBox:
    def __init__(self, tmp_path: Path) -> None:
        self.tmp_path = tmp_path
        self.log = tmp_path / "calls.jsonl"
        self.config = tmp_path / "responses.json"
        self.config.write_text("{}", encoding="utf-8")
        self.cmd = tmp_path / "VBoxManage.cmd"
        self.cmd.write_text(
            f'@echo off\r\n"{sys.executable}" "{FAKE_SCRIPT}" %*\r\n',
            encoding="utf-8",
        )

    def response(self, key: str, *, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
        data = json.loads(self.config.read_text(encoding="utf-8"))
        data[key] = {"stdout": stdout, "stderr": stderr, "returncode": returncode}
        self.config.write_text(json.dumps(data), encoding="utf-8")

    def calls(self) -> list[list[str]]:
        if not self.log.exists():
            return []
        return [json.loads(line)["args"] for line in self.log.read_text(encoding="utf-8").splitlines() if line]

    @property
    def last_args(self) -> list[str]:
        calls = self.calls()
        return calls[-1] if calls else []


@pytest.fixture
def fake(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> FakeVBox:
    f = FakeVBox(tmp_path)
    monkeypatch.setenv("FAKE_VBOX_LOG", str(f.log))
    monkeypatch.setenv("FAKE_VBOX_CONFIG", str(f.config))
    return f


@pytest.fixture
def settings(fake: FakeVBox, tmp_path: Path) -> Settings:
    return Settings.from_env(
        {
            "VBOX_MANAGE_PATH": str(fake.cmd),
            "VBOX_MCP_AUDIT_LOG": str(tmp_path / "audit.log"),
        }
    )
