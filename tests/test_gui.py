from __future__ import annotations

import struct
import sys
from pathlib import Path

import pytest

from vbox_mcp import gui
from vbox_mcp.config import Settings
from vbox_mcp.gui import map_coords, png_size, scancodes_for, screenshot, send_keys
from vbox_mcp.vboxmanage import VBoxError


def test_map_coords_scales_and_centers() -> None:
    assert map_coords(400, 300, 800, 600, 1000, 1000) == (500, 500)
    assert map_coords(0, 0, 800, 600, 1000, 1000) == (0, 125)


def test_map_coords_clamps() -> None:
    assert map_coords(-50, -50, 800, 600, 800, 600) == (0, 0)
    assert map_coords(9999, 9999, 800, 600, 800, 600) == (799, 599)


def test_map_coords_rejects_zero_guest_size() -> None:
    with pytest.raises(VBoxError, match="dimensiones"):
        map_coords(1, 1, 0, 600, 800, 600)


def test_scancodes_for_letters_and_enter() -> None:
    assert scancodes_for("a") == ["1e", "9e"]
    assert scancodes_for("<enter>") == ["1c", "9c"]


def test_scancodes_for_shifted_and_uppercase() -> None:
    assert scancodes_for("A") == ["2a", "1e", "9e", "aa"]
    assert scancodes_for("!") == ["2a", "02", "82", "aa"]


def test_scancodes_for_unsupported_char() -> None:
    with pytest.raises(VBoxError, match="ASCII"):
        scancodes_for("ñ")


def test_png_size(tmp_path: Path) -> None:
    png = tmp_path / "x.png"
    png.write_bytes(
        b"\x89PNG\r\n\x1a\n"
        + b"\x00\x00\x00\x0dIHDR"
        + struct.pack(">II", 1024, 768)
        + b"\x08\x02\x00\x00\x00"
    )

    assert png_size(png) == (1024, 768)


def test_png_size_rejects_invalid_file(tmp_path: Path) -> None:
    png = tmp_path / "x.png"
    png.write_bytes(b"not a png")

    with pytest.raises(VBoxError, match="PNG"):
        png_size(png)


def test_screenshot_invokes_vbox_and_returns_existing_file(settings: Settings, fake) -> None:
    fake.response("default", touch_index=3)

    path = screenshot(settings, "Win10", display=0)

    assert path.exists()
    assert fake.calls()[-1][:3] == ["controlvm", "Win10", "screenshotpng"]
    assert fake.calls()[-1][4] == "0"


def test_screenshot_fails_when_file_missing(settings: Settings, fake) -> None:
    fake.response("default", stdout="no file")

    with pytest.raises(VBoxError, match="screenshot"):
        screenshot(settings, "Win10")


def test_screenshot_removes_temp_file_on_failure(
    settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setattr(gui.tempfile, "gettempdir", lambda: str(tmp_path))

    def fail(*args, **kwargs):
        raise VBoxError("boom")

    monkeypatch.setattr(gui, "run", fail)

    with pytest.raises(VBoxError, match="boom"):
        screenshot(settings, "Win10")

    shots = tmp_path / "vbox-mcp-shots"
    assert not shots.exists() or not list(shots.iterdir())


def test_send_keys_string_mode(settings: Settings, fake) -> None:
    send_keys(settings, "Win10", "hello", method="string")

    assert fake.last_args == ["controlvm", "Win10", "keyboardputstring", "hello"]


def test_send_keys_scancode_mode(settings: Settings, fake) -> None:
    send_keys(settings, "Win10", "a<enter>", method="scancode")

    assert fake.last_args[:3] == ["controlvm", "Win10", "keyboardputscancode"]
    assert fake.last_args[3:] == ["1e", "9e", "1c", "9c"]


def test_send_keys_auto_uses_scancode_for_tokens(settings: Settings, fake) -> None:
    send_keys(settings, "Win10", "<tab>")

    assert fake.last_args[:3] == ["controlvm", "Win10", "keyboardputscancode"]


def test_mouse_requires_windows(settings: Settings, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(gui.sys, "platform", "linux")

    with pytest.raises(VBoxError, match="Windows"):
        gui.mouse_move(settings, "Win10", 10, 10)


def test_mouse_click_maps_coordinates(settings: Settings, monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    shot = tmp_path / "shot.png"
    shot.write_bytes(b"x")
    calls: list[tuple] = []

    monkeypatch.setattr(gui.sys, "platform", "win32")
    monkeypatch.setattr(gui, "screenshot", lambda *a, **k: shot)
    monkeypatch.setattr(gui, "png_size", lambda path: (800, 600))
    monkeypatch.setattr(gui, "_client_size", lambda vm: (1000, 1000))
    monkeypatch.setattr(gui, "_click_at", lambda *args: calls.append(args))

    gui.mouse_click(settings, "Win10", 400, 300, button="left", double=False)

    assert calls == [("Win10", 500, 500, "left", False)]


def test_mouse_disabled_by_setting(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    settings = Settings(
        vboxmanage_path=tmp_path / "VBoxManage.exe",
        readonly=False,
        timeout_seconds=60,
        audit_log=tmp_path / "audit.log",
        allow_mouse=False,
        guest_user=None,
        guest_password=None,
    )
    monkeypatch.setattr(sys, "platform", "win32")

    with pytest.raises(VBoxError, match="ratón"):
        gui.mouse_move(settings, "Win10", 10, 10)

def test_largest_child_picks_display_area() -> None:
    assert gui._largest_child([(1, 0, 0, 100, 100), (2, 0, 0, 800, 600)]) == 2
    assert gui._largest_child([(1, 0, 0, 100, 100)]) == 1
    assert gui._largest_child([]) is None


def test_resolve_window_name_uses_registered_name(settings: Settings, fake) -> None:
    fake.response(
        "showvminfo UUID-1 --machinereadable",
        stdout='name="Windows 10"\n',
    )

    assert gui._resolve_window_name(settings, "UUID-1") == "Windows 10"


def test_foreground_ok_requires_visible_focused_window() -> None:
    class FakeUser32:
        def __init__(self, foreground: int, visible: bool = True, iconic: bool = False) -> None:
            self.foreground = foreground
            self.visible = visible
            self.iconic = iconic

        def GetForegroundWindow(self) -> int:
            return self.foreground

        def IsWindowVisible(self, hwnd: int) -> bool:
            return self.visible

        def IsIconic(self, hwnd: int) -> bool:
            return self.iconic

    assert gui._foreground_ok(7, FakeUser32(7)) is True
    assert gui._foreground_ok(7, FakeUser32(8)) is False
    assert gui._foreground_ok(7, FakeUser32(7, visible=False)) is False
    assert gui._foreground_ok(7, FakeUser32(7, iconic=True)) is False


def test_screenshots_do_not_collide(settings: Settings, fake) -> None:
    fake.response("default", touch_index=3)

    first = screenshot(settings, "Win10")
    second = screenshot(settings, "Win10")

    assert first != second
