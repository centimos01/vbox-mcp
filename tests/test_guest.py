from __future__ import annotations

import pytest

from vbox_mcp import guest
from vbox_mcp.config import Settings
from vbox_mcp.guest import guest_copy_from, guest_copy_to, guest_exec, password_file
from vbox_mcp.vboxmanage import VBoxError


def test_password_file_contains_secret_and_is_removed() -> None:
    with password_file("hunter2") as path:
        with open(path, encoding="utf-8") as fh:
            assert fh.read() == "hunter2"
        kept = path

    assert not __import__("os").path.exists(kept)


def test_password_file_removed_on_exception() -> None:
    kept = None
    with pytest.raises(RuntimeError):
        with password_file("hunter2") as path:
            kept = path
            raise RuntimeError("boom")

    assert kept is not None
    assert not __import__("os").path.exists(kept)


def test_guest_exec_uses_password_file_not_argv(settings: Settings, fake) -> None:
    fake.response("default", stdout="hello\nExit code: 0\n")

    result = guest_exec(
        settings,
        "Win10",
        user="Administrador",
        password="hunter2",
        exe="cmd.exe",
        args=["/c", "dir"],
    )

    call = fake.calls()[-1]
    assert call[:5] == ["guestcontrol", "Win10", "run", "--exe", "cmd.exe"]
    assert "--username" in call
    assert call[call.index("--username") + 1] == "Administrador"
    assert "--passwordfile" in call
    assert "hunter2" not in call
    password_path = call[call.index("--passwordfile") + 1]
    assert not __import__("os").path.exists(password_path)
    assert result == {"exit_code": 0, "stdout": "hello\nExit code: 0\n", "stderr": ""}


def test_guest_exec_translates_missing_guest_additions(settings: Settings, fake) -> None:
    fake.response(
        "default",
        stderr="VBoxManage: error: The guest execution service is not ready (yet)",
        returncode=1,
    )

    with pytest.raises(VBoxError, match="Guest Additions"):
        guest_exec(settings, "Win10", user="u", password="p", exe="cmd.exe")


def test_guest_exec_translates_bad_credentials(settings: Settings, fake) -> None:
    fake.response(
        "default",
        stderr="VBoxManage: error: Invalid user name or password",
        returncode=1,
    )

    with pytest.raises(VBoxError, match="[Cc]redenciales"):
        guest_exec(settings, "Win10", user="u", password="p", exe="cmd.exe")


def test_guest_exec_nonzero_guest_exit_is_returned(settings: Settings, fake) -> None:
    fake.response("default", stdout="fallo\n", returncode=39)
    result = guest_exec(settings, "Win10", user="u", password="p", exe="cmd.exe")
    assert result["exit_code"] == 7
    assert "fallo" in result["stdout"]


def test_guest_exec_maps_low_guest_exit(settings: Settings, fake) -> None:
    fake.response("default", stdout="", returncode=33)
    result = guest_exec(settings, "Win10", user="u", password="p", exe="cmd.exe")
    assert result["exit_code"] == 1


def test_guest_exec_ignores_guest_printed_exit_marker(settings: Settings, fake) -> None:
    fake.response("default", stdout="Exit code: 0\n", returncode=39)
    result = guest_exec(settings, "Win10", user="u", password="p", exe="cmd.exe")
    assert result["exit_code"] == 7


def test_guest_exec_vbox_timeout_raises(settings: Settings, fake) -> None:
    fake.response("default", stderr="timed out", returncode=20)
    with pytest.raises(VBoxError, match="tiempo|timeout|20"):
        guest_exec(settings, "Win10", user="u", password="p", exe="cmd.exe")


def test_guest_copy_to(settings: Settings, fake, tmp_path) -> None:
    source = tmp_path / "script.sh"
    source.write_text("echo hi")

    guest_copy_to(
        settings,
        "Ubuntu",
        user="ubuntu",
        password="p",
        host_path=str(source),
        guest_path="/tmp/script.sh",
    )

    call = fake.calls()[-1]
    assert call[:5] == ["guestcontrol", "Ubuntu", "copyto", str(source), "/tmp/script.sh"]
    assert call[5:7] == ["--username", "ubuntu"]
    assert "p" not in [str(part) for part in call if part == "p"]


def test_guest_copy_to_requires_existing_host_file(settings: Settings, tmp_path) -> None:
    with pytest.raises(VBoxError, match="host_path"):
        guest_copy_to(
            settings,
            "Ubuntu",
            user="ubuntu",
            password="p",
            host_path=str(tmp_path / "missing"),
            guest_path="/tmp/x",
        )


def test_guest_copy_from(settings: Settings, fake, tmp_path) -> None:
    target = tmp_path / "out" / "file.txt"

    guest_copy_from(
        settings,
        "Ubuntu",
        user="ubuntu",
        password="p",
        guest_path="/tmp/file.txt",
        host_path=str(target),
    )

    assert target.parent.is_dir()
    call = fake.calls()[-1]
    assert call[:4] == ["guestcontrol", "Ubuntu", "copyfrom", "/tmp/file.txt"]
    assert str(target) in call


def test_guest_exec_redacts_password_from_audit(settings: Settings, fake) -> None:
    fake.response("default", stdout="ok")

    guest_exec(settings, "Win10", user="u", password="super-secret", exe="cmd.exe")

    assert "super-secret" not in fake.log.read_text(encoding="utf-8")

def test_guest_exec_uses_supported_cwd_flag(settings: Settings, fake) -> None:
    fake.response("default", stdout="ok")

    guest_exec(
        settings,
        "Ubuntu",
        user="u",
        password="p",
        exe="/bin/ls",
        working_dir="/tmp",
    )

    call = fake.calls()[-1]
    assert "--cwd" in call
    assert call[call.index("--cwd") + 1] == "/tmp"
    assert "--working-dir" not in call


def test_guest_exec_unknown_vbox_failure_raises(settings: Settings, fake) -> None:
    fake.response("default", stderr="VBoxManage: error: something unexpected", returncode=1)

    with pytest.raises(VBoxError, match="something unexpected"):
        guest_exec(settings, "Win10", user="u", password="p", exe="cmd.exe")
