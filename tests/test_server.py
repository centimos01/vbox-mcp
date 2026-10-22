from __future__ import annotations

import asyncio
import json
import os
import queue
import subprocess
import sys
import threading
from pathlib import Path

import pytest
from mcp.types import LATEST_PROTOCOL_VERSION

from vbox_mcp.config import Settings
from vbox_mcp.server import build_server

ROOT = Path(__file__).resolve().parents[1]

READ_ONLY_TOOLS = {
    "vbox_list_vms",
    "vbox_vm_info",
    "vbox_list_ostypes",
    "vbox_snapshot_list",
    "vbox_list_networks",
    "vbox_guest_ip",
    "vbox_screenshot",
}

EXPECTED_TOOLS = READ_ONLY_TOOLS | {
    "vbox_start_vm",
    "vbox_stop_vm",
    "vbox_pause_vm",
    "vbox_resume_vm",
    "vbox_reset_vm",
    "vbox_create_vm",
    "vbox_modify_vm",
    "vbox_clone_vm",
    "vbox_delete_vm",
    "vbox_attach_iso",
    "vbox_detach_iso",
    "vbox_shared_folder_add",
    "vbox_shared_folder_remove",
    "vbox_nat_port_forward_add",
    "vbox_nat_port_forward_remove",
    "vbox_snapshot_take",
    "vbox_snapshot_restore",
    "vbox_snapshot_delete",
    "vbox_guest_exec",
    "vbox_guest_copy_to",
    "vbox_guest_copy_from",
    "vbox_send_keys",
    "vbox_mouse_move",
    "vbox_mouse_click",
}


def tool_names(settings: Settings) -> set[str]:
    server = build_server(settings)
    return {tool.name for tool in asyncio.run(server.list_tools())}


def call(settings: Settings, name: str, arguments: dict):
    server = build_server(settings)
    return asyncio.run(server.call_tool(name, arguments))


def text_of(result) -> str:
    return "\n".join(getattr(item, "text", "") for item in result.content)


def test_all_tools_registered_when_writable(settings: Settings) -> None:
    assert tool_names(settings) == EXPECTED_TOOLS


def test_readonly_hides_mutating_tools(settings: Settings, tmp_path: Path) -> None:
    readonly = Settings(
        vboxmanage_path=settings.vboxmanage_path,
        readonly=True,
        timeout_seconds=settings.timeout_seconds,
        audit_log=tmp_path / "audit.log",
        allow_mouse=True,
        guest_user=None,
        guest_password=None,
    )

    assert tool_names(readonly) == READ_ONLY_TOOLS


def test_list_vms_tool(settings: Settings, fake) -> None:
    fake.response("list vms", stdout='"Win10" {11111111-1111-1111-1111-111111111111}\n')
    fake.response("list runningvms", stdout="")

    result = call(settings, "vbox_list_vms", {})

    assert not result.is_error
    assert "Win10" in text_of(result)


def test_delete_without_confirm_does_nothing(settings: Settings, fake) -> None:
    result = call(settings, "vbox_delete_vm", {"vm": "Win10"})

    assert "confirmation_required" in text_of(result)
    assert fake.calls() == []


def test_delete_with_confirm_executes(settings: Settings, fake) -> None:
    result = call(settings, "vbox_delete_vm", {"vm": "Win10", "confirm": True})

    assert not result.is_error
    assert fake.calls()[-1] == ["unregistervm", "Win10"]
    assert settings.audit_log.exists()


def test_readonly_mutating_tool_is_not_available(settings: Settings, tmp_path: Path) -> None:
    readonly = Settings(
        vboxmanage_path=settings.vboxmanage_path,
        readonly=True,
        timeout_seconds=settings.timeout_seconds,
        audit_log=tmp_path / "audit.log",
        allow_mouse=True,
        guest_user=None,
        guest_password=None,
    )

    with pytest.raises(Exception):
        call(readonly, "vbox_start_vm", {"vm": "Win10"})


def test_screenshot_returns_image_content(settings: Settings, fake) -> None:
    fake.response("default", touch_index=3)

    result = call(settings, "vbox_screenshot", {"vm": "Win10"})

    assert result.content[0].type == "image"


def test_stdio_handshake_lists_tools(settings: Settings, fake) -> None:
    fake.response("list vms", stdout='"Win10" {11111111-1111-1111-1111-111111111111}\n')
    fake.response("list runningvms", stdout="")

    env = {
        **os.environ,
        "PYTHONPATH": str(ROOT / "src"),
        "VBOX_MANAGE_PATH": str(fake.cmd),
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "vbox_mcp"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=str(ROOT),
        env=env,
        text=True,
        encoding="utf-8",
    )
    messages: queue.Queue[dict] = queue.Queue()

    def reader() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            line = line.strip()
            if line:
                messages.put(json.loads(line))

    threading.Thread(target=reader, daemon=True).start()

    def send(payload: dict) -> None:
        assert process.stdin is not None
        process.stdin.write(json.dumps(payload) + "\n")
        process.stdin.flush()

    def wait_for(request_id: int) -> dict:
        while True:
            message = messages.get(timeout=15)
            if message.get("id") == request_id:
                return message

    try:
        send(
            {
                "jsonrpc": "2.0",
                "id": 1,
                "method": "initialize",
                "params": {
                    "protocolVersion": LATEST_PROTOCOL_VERSION,
                    "capabilities": {},
                    "clientInfo": {"name": "pytest", "version": "1"},
                },
            }
        )
        init = wait_for(1)
        assert "result" in init

        send({"jsonrpc": "2.0", "method": "notifications/initialized"})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        listing = wait_for(2)

        names = {tool["name"] for tool in listing["result"]["tools"]}
        assert names == EXPECTED_TOOLS

        send(
            {
                "jsonrpc": "2.0",
                "id": 3,
                "method": "tools/call",
                "params": {"name": "vbox_list_vms", "arguments": {}},
            }
        )
        called = wait_for(3)
        assert "Win10" in json.dumps(called["result"])
    finally:
        process.terminate()
        process.wait(timeout=10)
