# vbox-mcp Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Servidor MCP en Python que expone control completo de VirtualBox local a OpenCode por stdio, incluyendo screenshots y entrada de teclado/ratón.

**Architecture:** Capas aisladas: `config` (detección y settings), `vboxmanage` (único módulo que lanza procesos), `safety` (readonly, confirmaciones, auditoría), `gui` (Win32 + funciones puras), `server` (tools MCP sobre `MCPServer` del SDK 2.x).

**Tech Stack:** Python 3.11+, SDK `mcp>=2,<3` (`mcp.server.mcpserver.MCPServer`), Pydantic v2, pytest + pytest-asyncio, `VBoxManage` 7.x.

**Spec:** `docs/superpowers/specs/2026-10-22-virtualbox-mcp-design.md`

## Global Constraints

- Solo stdio; sin dependencias nativas más allá de `mcp`.
- Nunca `shell=True`; siempre listas de argumentos.
- `VBOX_MCP_READONLY=true` oculta las tools mutantes.
- Tools destructivas exigen `confirm=true`.
- Contraseñas guest por `--passwordfile` temporal; nunca en argv ni logs.
- Timeout configurable por comando, defecto 60 s; salida máxima 1 MB.
- Nombres de tools con prefijo `vbox_`.
- Ratón solo Windows y VM en modo GUI.

## Review Focus

- VM inexistente o nombre ambiguo → error claro, sin traza.
- VM apagada con `screenshot`/`send_keys` → error que indique arrancarla.
- Guest Additions ausentes → error que indique instalarlas, no timeout opaco.
- `VBoxManage` ausente o ruta con espacios → arranque del servidor intacto y error accionable.
- Salida con caracteres no UTF-8 o líneas vacías → parseo tolerante, sin excepción.

---

### Task 1: Scaffold, settings y detección de VBoxManage

**Files:**
- Create: `pyproject.toml`, `src/vbox_mcp/__init__.py`, `src/vbox_mcp/config.py`, `tests/conftest.py`, `tests/test_config.py`

**Interfaces:**
- Produces: `Settings` dataclass con `vboxmanage_path: Path | None`, `readonly: bool`, `timeout_seconds: int`, `audit_log: Path`, `allow_mouse: bool`, `guest_user: str | None`, `guest_password: str | None`; `Settings.from_env(env: Mapping[str,str] | None = None) -> Settings`; `find_vboxmanage(env, exists=Path.exists) -> Path | None`.

- [ ] **Step 1: Test de detección por variable de entorno, PATH y ruta estándar**

```python
def test_env_var_wins(tmp_path, monkeypatch):
    fake = tmp_path / "VBoxManage.exe"; fake.write_text("")
    s = Settings.from_env({"VBOX_MANAGE_PATH": str(fake)})
    assert s.vboxmanage_path == fake

def test_readonly_parsing():
    assert Settings.from_env({"VBOX_MCP_READONLY": "true"}).readonly is True
    assert Settings.from_env({"VBOX_MCP_READONLY": "0"}).readonly is False
```

- [ ] **Step 2:** `pytest tests/test_config.py -v` → FAIL (`ModuleNotFoundError`).
- [ ] **Step 3:** Implementar `Settings` y `find_vboxmanage` con orden: env → `shutil.which("VBoxManage")` → rutas estándar Windows/Linux/macOS.
- [ ] **Step 4:** `pytest tests/test_config.py -v` → PASS.
- [ ] **Step 5:** Commit `feat: scaffold y configuracion`.

### Task 2: Runner de VBoxManage y consultas de solo lectura

**Files:**
- Create: `src/vbox_mcp/vboxmanage.py`, `src/vbox_mcp/parsing.py`, `tests/fake_vboxmanage.py`, `tests/test_vboxmanage.py`, `tests/test_parsing.py`

**Interfaces:**
- Produces: `VBoxError(Exception)` con `.returncode`, `.stderr`; `run(args: list[str], *, timeout: int | None = None, settings: Settings | None = None) -> str`; `parse_vm_list(text) -> list[dict]`; `parse_machine_readable(text) -> dict[str,str]`; `parse_ostypes(text) -> list[dict]`; `list_vms(settings, running_only=False) -> list[dict]`; `vm_info(settings, vm) -> dict`; `list_ostypes(settings) -> list[dict]`; `snapshot_list(settings, vm) -> list[dict]`; `list_networks(settings) -> dict`; `guest_ip(settings, vm) -> str | None`.

- [ ] **Step 1:** Test con fake que registra argv:

```python
def test_list_vms_parses_names_and_uuids(settings, fake):
    fake.set_output("list vms", '"Win10" {abc}\n"Ubuntu" {def}\n')
    vms = list_vms(settings)
    assert vms == [{"name": "Win10", "uuid": "abc", "state": "unknown"}, ...]
    assert fake.last_args == ["list", "vms"]
```

- [ ] **Step 2:** `pytest tests/test_parsing.py tests/test_vboxmanage.py -v` → FAIL.
- [ ] **Step 3:** Implementar runner (`subprocess.run`, `text=False` + decode `utf-8`/`errors="replace"`, truncado a 1 MB) y parseos. `list_vms` combina `list vms` + `list runningvms` para `state`.
- [ ] **Step 4:** Tests → PASS.
- [ ] **Step 5:** Commit `feat: runner y consultas de solo lectura`.

### Task 3: Seguridad (readonly, confirmación, auditoría)

**Files:**
- Create: `src/vbox_mcp/safety.py`, `tests/test_safety.py`

**Interfaces:**
- Produces: `ConfirmationRequired(Exception)`; `ensure_writable(settings)`; `require_confirm(confirm: bool, action: str, target: str, effects: list[str]) -> None`; `audit(settings, tool: str, args: dict, result: str, duration_ms: int) -> None`; `redact(value: Any) -> Any`.

- [ ] **Step 1:** Tests: readonly lanza `VBoxError`; `require_confirm(False, ...)` lanza `ConfirmationRequired` con `.effects`; `redact` sustituye claves `password`, `passwd`, `secret`, `token` por `***`; audit escribe JSONL.
- [ ] **Step 2:** `pytest tests/test_safety.py -v` → FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** PASS.
- [ ] **Step 5:** Commit `feat: capa de seguridad y auditoria`.

### Task 4: Ciclo de vida

**Files:**
- Create: `src/vbox_mcp/lifecycle.py`, `tests/test_lifecycle.py`
- Modify: `src/vbox_mcp/vboxmanage.py` (helper `run_checked`)

**Interfaces:**
- Produces: `start_vm(settings, vm, mode="headless") -> dict`; `stop_vm(settings, vm, mode="acpi") -> dict`; `pause_vm`, `resume_vm`, `reset_vm`; `create_vm(settings, name, ostype, cpus=2, memory_mb=2048, disk_mb=0, iso=None, network="nat") -> dict`; `modify_vm(settings, vm, cpus=None, memory_mb=None, nic=None) -> dict`; `clone_vm(settings, source, name, mode="full", snapshot=None) -> dict`; `delete_vm(settings, vm, delete_disks=False) -> dict`.

- [ ] **Step 1:** Tests de argv exacto para `startvm --type headless`, `controlvm acpipowerbutton`, `controlvm poweroff`, `createvm --register`, `clonemedium`/`clonevm`, `unregistervm --delete` solo con `delete_disks=True`.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** Implementar sin validación de estado redundante (VBox ya falla).
- [ ] **Step 4:** PASS.
- [ ] **Step 5:** Commit `feat: tools de ciclo de vida`.

### Task 5: Almacenamiento y red

**Files:**
- Create: `src/vbox_mcp/storage.py`, `tests/test_storage.py`

**Interfaces:**
- Produces: `attach_iso(settings, vm, iso_path, controller="sata", port=1)`; `detach_iso(settings, vm, controller="sata", port=1)`; `shared_folder_add(settings, vm, name, host_path, automount=True, readonly=False)`; `shared_folder_remove(settings, vm, name)`; `nat_port_forward_add(settings, vm, rule_name, protocol, host_port, guest_port, guest_ip="")`; `nat_port_forward_remove(settings, vm, rule_name)`.

- [ ] **Step 1:** Tests de argv para `storageattach --medium`/`none`, `sharedfolder add --automount`, `modifyvm --natpf1`/`--natpf1 delete`. Validar que `iso_path` existe antes de invocar.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** PASS.
- [ ] **Step 5:** Commit `feat: almacenamiento y red`.

### Task 6: Snapshots

**Files:**
- Create: `src/vbox_mcp/snapshots.py`, `tests/test_snapshots.py`

**Interfaces:**
- Produces: `snapshot_take(settings, vm, name, description="")`; `snapshot_restore(settings, vm, name)`; `snapshot_delete(settings, vm, name)`.

- [ ] **Step 1:** Tests de argv (`snapshot take/restore/delete`).
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** PASS.
- [ ] **Step 5:** Commit `feat: snapshots`.

### Task 7: Guest control

**Files:**
- Create: `src/vbox_mcp/guest.py`, `tests/test_guest.py`

**Interfaces:**
- Produces: `guest_exec(settings, vm, user, password, exe, args=[], timeout=60, env={}, working_dir=None) -> dict`; `guest_copy_to(...)`; `guest_copy_from(...)`; helper `password_file(password) -> contextmanager[str]` con borrado garantizado.

- [ ] **Step 1:** Tests: el argv contiene `--passwordfile` y **no** la contraseña; el archivo temporal se borra tras éxito y tras excepción; `guest_exec` devuelve `exit_code` y captura stdout/stderr; fallo de Guest Additions se traduce a mensaje accionable.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** Implementar.
- [ ] **Step 4:** PASS.
- [ ] **Step 5:** Commit `feat: guest control`.

### Task 8: GUI (screenshot, teclado, ratón)

**Files:**
- Create: `src/vbox_mcp/gui.py`, `tests/test_gui.py`

**Interfaces:**
- Produces: `screenshot(settings, vm, display=0) -> Path`; `send_keys(settings, vm, text, delay_ms=50, method="string") -> dict`; `mouse_move(settings, vm, x, y)`; `mouse_click(settings, vm, x, y, button="left", double=False)`; `map_coords(x, y, guest_w, guest_h, client_w, client_h) -> tuple[int,int]`; `scancodes_for(text) -> list[str]`.

- [ ] **Step 1:** Tests puros: `map_coords` escala y recorta a límites; `scancodes_for("a<enter>")` produce scancodes US + token; `screenshot` usa `controlvm ... screenshotpng` y falla claro si el archivo no se creó.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** Implementar; ratón con `ctypes.windll.user32` detrás de `if sys.platform == "win32"`, error claro en otros SO.
- [ ] **Step 4:** PASS.
- [ ] **Step 5:** Commit `feat: captura y entrada GUI`.

### Task 9: Servidor MCP

**Files:**
- Create: `src/vbox_mcp/server.py`, `src/vbox_mcp/__main__.py`, `tests/test_server.py`

**Interfaces:**
- Produces: `build_server(settings: Settings | None = None) -> MCPServer`; 28 tools `vbox_*` con validación Pydantic y `confirm` donde aplica; tools de solo lectura devuelven dict; `vbox_screenshot` devuelve `Image`.

- [ ] **Step 1:** Test de handshake real por stdio: lanzar `.venv/python -m vbox_mcp` con `VBOX_MANAGE_PATH` apuntando al fake, enviar `initialize`, `tools/list`, `tools/call` de `vbox_list_vms`; verificar 28 tools y resultado.
- [ ] **Step 2:** FAIL.
- [ ] **Step 3:** Implementar `build_server`, registrar tools y envolver mutantes con `ensure_writable` + `require_confirm` + `audit`.
- [ ] **Step 4:** PASS.
- [ ] **Step 5:** Commit `feat: servidor MCP y tools`.

### Task 10: Instalación, OpenCode y smoke real

**Files:**
- Create: `scripts/install.ps1`, `README.md`, `tests/test_integration_readonly.py`

**Interfaces:**
- Produces: script idempotente que crea `.venv`, instala, y muestra el bloque de configuración; README con uso y ejemplos.

- [ ] **Step 1:** Test de integración marcado `integration`: `list_vms(real_settings)` devuelve ≥1 VM; `vm_info` de la primera no lanza.
- [ ] **Step 2:** Ejecutar `pytest -m integration -v` → PASS con VirtualBox real.
- [ ] **Step 3:** Escribir `install.ps1` y README.
- [ ] **Step 4:** Registrar en OpenCode (`opencode mcp add` o config) y verificar `opencode mcp list` → connected.
- [ ] **Step 5:** Commit `feat: instalacion y documentacion`.

## Verificación final

- `pytest` completo en verde.
- `opencode mcp list` muestra `vbox` conectado.
- El agente lista las 6 VMs reales y obtiene `vbox_vm_info` de una.
- `vbox_delete_vm` sin `confirm` no ejecuta nada.
