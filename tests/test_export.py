from __future__ import annotations

import pytest

from vbox_mcp.config import Settings
from vbox_mcp.export import export_vm, import_vm
from vbox_mcp.vboxmanage import VBoxError


def test_export_vm_ova(settings: Settings, fake) -> None:
    result = export_vm(settings, "Win10", "C:/exports/win10.ova", fmt="ova", manifest=True, description="Test VM")

    # Path separators may vary by platform
    assert fake.last_args[0] == "export"
    assert fake.last_args[1] == "Win10"
    assert fake.last_args[2] == "--output"
    assert fake.last_args[4] == "--ova"
    assert "--no-manifest" not in fake.last_args
    # Output path may have platform-specific separators
    assert result["vm"] == "Win10"
    assert result["action"] == "export"
    assert result["format"] == "ova"
    assert "win10.ova" in result["output"]


def test_export_vm_ovf20(settings: Settings, fake) -> None:
    export_vm(settings, "Win10", "C:/exports/win10.ovf", fmt="ovf20", manifest=False)

    assert fake.last_args[0] == "export"
    assert fake.last_args[1] == "Win10"
    assert fake.last_args[2] == "--output"
    assert fake.last_args[4] == "--ovf20"
    assert fake.last_args[5] == "--no-manifest"


def test_export_vm_ovf09(settings: Settings, fake) -> None:
    export_vm(settings, "Win10", "C:/exports/win10.ovf", fmt="ovf09")

    assert "--ovf09" in fake.last_args


def test_export_vm_ovf10(settings: Settings, fake) -> None:
    export_vm(settings, "Win10", "C:/exports/win10.ovf", fmt="ovf10")

    assert "--ovf10" in fake.last_args


def test_export_vm_rejects_bad_format(settings: Settings) -> None:
    with pytest.raises(VBoxError, match="fmt"):
        export_vm(settings, "Win10", "out.ova", fmt="bad")


def test_export_vm_creates_output_dir(settings: Settings, fake, tmp_path) -> None:
    out = tmp_path / "subdir" / "win10.ova"
    export_vm(settings, "Win10", str(out))

    assert fake.last_args[3] == str(out)


def test_import_vm_basic(settings: Settings, fake, tmp_path) -> None:
    ova = tmp_path / "vm.ova"
    ova.write_bytes(b"ova")

    result = import_vm(settings, str(ova))

    assert fake.last_args == ["import", str(ova)]
    assert result == {"action": "import", "source": str(ova), "name": "(auto)"}


def test_import_vm_with_name(settings: Settings, fake, tmp_path) -> None:
    ova = tmp_path / "vm.ova"
    ova.write_bytes(b"ova")

    import_vm(settings, str(ova), name="MyVM")

    assert fake.last_args == ["import", str(ova), "--vsys", "0", "--vmname", "MyVM"]


def test_import_vm_with_base_folder(settings: Settings, fake, tmp_path) -> None:
    ova = tmp_path / "vm.ova"
    ova.write_bytes(b"ova")
    base = tmp_path / "vms"

    import_vm(settings, str(ova), base_folder=str(base))

    assert fake.last_args == ["import", str(ova), "--vsys", "0", "--basefolder", str(base)]


def test_import_vm_with_cpus_memory(settings: Settings, fake, tmp_path) -> None:
    ova = tmp_path / "vm.ova"
    ova.write_bytes(b"ova")

    import_vm(settings, str(ova), cpus=4, memory_mb=8192)

    assert fake.last_args[:6] == ["import", str(ova), "--vsys", "0", "--cpus", "4"]
    assert "--memory" in fake.last_args
    assert fake.last_args[fake.last_args.index("--memory") + 1] == "8192"


def test_import_vm_rejects_missing_file(settings: Settings, tmp_path) -> None:
    with pytest.raises(VBoxError, match="No existe el archivo"):
        import_vm(settings, str(tmp_path / "missing.ova"))