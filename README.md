# vbox-mcp

Servidor MCP (Model Context Protocol) para controlar VirtualBox local desde OpenCode u otros clientes MCP. Habla por **stdio** y usa `VBoxManage` como única dependencia externa.

Incluye ciclo de vida completo, snapshots, ISOs, carpetas compartidas, red NAT, ejecución dentro del guest y visión/entrada GUI (screenshot, teclado y ratón).

## Requisitos

- Windows, Linux o macOS con VirtualBox 7.x.
- Python 3.11+.
- Para `guest_exec`, `guest_copy_*` y carpetas compartidas: Guest Additions en la VM.
- Para `vbox_mouse_*`: Windows, VM arrancada con `mode="gui"` y `VBOX_MCP_ALLOW_MOUSE` activo.

## Instalación

```powershell
cd C:\Users\Usuario\vbox-mcp
.\scripts\install.ps1
```

El script crea `.venv`, instala el paquete en modo editable y muestra el comando de registro.

Manual:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

## Registro en OpenCode

```powershell
opencode mcp add vbox --global -- "C:\Users\Usuario\vbox-mcp\.venv\Scripts\python.exe" -m vbox_mcp
opencode mcp list
```

O en `opencode.json`:

```json
{
  "mcp": {
    "servers": {
      "vbox": {
        "type": "local",
        "command": ["C:\\Users\\Usuario\\vbox-mcp\\.venv\\Scripts\\python.exe", "-m", "vbox_mcp"]
      }
    }
  }
}
```

## Configuración

Todo es opcional por variables de entorno:

| Variable | Defecto | Descripción |
|---|---|---|
| `VBOX_MANAGE_PATH` | autodetección | Ruta a `VBoxManage(.exe)`. |
| `VBOX_MCP_READONLY` | `false` | `true` oculta todas las tools mutantes del catálogo. |
| `VBOX_MCP_TIMEOUT_SECONDS` | `60` | Timeout por invocación de `VBoxManage`. |
| `VBOX_MCP_AUDIT_LOG` | `%LOCALAPPDATA%\vbox-mcp\audit.log` | Log JSONL de llamadas (secretos redactados). |
| `VBOX_MCP_ALLOW_MOUSE` | `true` | Permite mover/hacer clic con el ratón. |
| `VBOX_MCP_GUEST_USER` | — | Usuario por defecto sugerido para el guest. |
| `VBOX_MCP_GUEST_PASSWORD` | — | Contraseña por defecto sugerida para el guest. |

La autodetección busca primero `VBOX_MANAGE_PATH`, luego `PATH` y finalmente las rutas estándar de VirtualBox.

Las operaciones largas (`vbox_clone_vm`, `vbox_delete_vm`, `vbox_snapshot_delete`, `vbox_guest_copy_to` y `vbox_guest_copy_from`) aceptan `timeout_seconds` (600 por defecto). El resto usa `VBOX_MCP_TIMEOUT_SECONDS`.

## Tools

### Lectura (siempre disponibles)

| Tool | Qué hace |
|---|---|
| `vbox_list_vms` | Lista VMs y estado (`running`/`stopped`). |
| `vbox_vm_info` | Configuración y estado de una VM. |
| `vbox_list_ostypes` | Tipos de SO válidos para crear VMs. |
| `vbox_snapshot_list` | Snapshots de una VM. |
| `vbox_list_networks` | Interfaces host-only y redes NAT. |
| `vbox_guest_ip` | IPv4 reportada por Guest Additions. |
| `vbox_screenshot` | PNG de la pantalla de la VM. |

### Ciclo de vida

`vbox_start_vm`, `vbox_stop_vm`, `vbox_pause_vm`, `vbox_resume_vm`, `vbox_reset_vm`, `vbox_create_vm`, `vbox_modify_vm`, `vbox_clone_vm`, `vbox_delete_vm`.

### Almacenamiento y red

`vbox_attach_iso`, `vbox_detach_iso`, `vbox_shared_folder_add`, `vbox_shared_folder_remove`, `vbox_nat_port_forward_add`, `vbox_nat_port_forward_remove`.

### Snapshots

`vbox_snapshot_take`, `vbox_snapshot_restore`, `vbox_snapshot_delete`.

### Guest control (Guest Additions)

`vbox_guest_exec`, `vbox_guest_copy_to`, `vbox_guest_copy_from`.

### GUI

`vbox_send_keys`, `vbox_mouse_move`, `vbox_mouse_click`.

Total: **31 tools**.

## Seguridad

- `VBOX_MCP_READONLY=true` elimina las tools mutantes del catálogo.
- Las operaciones destructivas devuelven `status: "confirmation_required"` si no se envían con `confirm=true`:
  - `vbox_delete_vm`
  - `vbox_stop_vm` con `mode="poweroff"`
  - `vbox_reset_vm`
  - `vbox_snapshot_restore`
  - `vbox_snapshot_delete`
- Los fallos de `VBoxManage` se devuelven como error de tool (`isError`) con el mensaje original, para que el agente pueda corregir la llamada.
- Para `network="bridged"` u `"hostonly"` en `vbox_create_vm`/`vbox_modify_vm` hay que indicar `adapter` (por ejemplo `"Ethernet"` o `"vboxnet0"`); si falta, la tool falla con un mensaje accionable.
- Las reglas NAT aceptan `host_ip` para limitar la escucha a una interfaz concreta (por ejemplo `127.0.0.1`).
- Ninguna tool usa `shell=True`; los argumentos van en lista.
- Las contraseñas del guest se pasan por un archivo temporal (`--passwordfile`) y se borran siempre; nunca van en `argv` ni en el log.
- Cada llamada se audita en JSONL con `password`, `passwd`, `secret`, `token` y similares redactados.

## Ejemplos

Listar y arrancar:

```text
vbox_list_vms()
vbox_start_vm(vm="windows 10", mode="gui")
vbox_screenshot(vm="windows 10")
```

Crear una VM con disco e ISO:

```text
vbox_create_vm(
  name="ubuntu-test",
  ostype="Ubuntu24_LTS_64",
  cpus=4,
  memory_mb=8192,
  disk_mb=25600,
  iso="C:\\ISOs\\ubuntu-24.04.iso"
)
```

Enviar teclado y ratón:

```text
vbox_send_keys(vm="windows 10", text="<enter>")
vbox_send_keys(vm="windows 10", text="hola mundo")
vbox_mouse_click(vm="windows 10", x=640, y=400)
```

Ejecutar dentro del guest:

```text
vbox_guest_exec(
  vm="ubuntu-test",
  user="ubuntu",
  password="...",
  exe="/bin/sh",
  args=["-c", "uname -a"]
)
```

Añadir una regla NAT solo para localhost:

```text
vbox_nat_port_forward_add(
  vm="ubuntu-test",
  rule_name="ssh",
  protocol="tcp",
  host_port=2222,
  guest_port=22,
  host_ip="127.0.0.1"
)
```

## Desarrollo

```powershell
.\.venv\Scripts\python.exe -m pytest            # unidad, sin VirtualBox
.\.venv\Scripts\python.exe -m pytest -m integration -v   # smoke real, solo lectura
```

## Limitaciones

- El ratón solo funciona en Windows: mueve el cursor real sobre la ventana de VirtualBox. No uses la máquina mientras un agente controle el ratón.
- `vbox_screenshot`, `vbox_send_keys` y `vbox_mouse_*` requieren la VM encendida (no sirven en estado guardado).
- Sin Guest Additions, `vbox_guest_*` y las carpetas compartidas fallan con un mensaje accionable.
- Las carpetas compartidas añadidas con la VM encendida son `--transient` (VirtualBox no permite persistirlas en caliente); vuelven a desaparecer al apagar la VM.
- El servidor no instala Guest Additions ni crea controladores SATA en VMs ya existentes; `vbox_create_vm` sí lo hace.
