# vbox-mcp

Servidor MCP (Model Context Protocol) para controlar VirtualBox local desde OpenCode u otros clientes MCP. Habla por **stdio** y usa `VBoxManage` como única dependencia externa.

Incluye ciclo de vida completo, snapshots, ISOs, carpetas compartidas, red NAT, ejecución dentro del guest y visión/entrada GUI (screenshot, teclado y ratón).

## Requisitos

- Windows, Linux o macOS con VirtualBox 7.x.
- Python 3.11+.
- Para `guest_exec`, `guest_copy_*` y carpetas compartidas: Guest Additions en la VM.
- Para `vbox_mouse_*`: Windows, VM arrancada con `mode="gui"`, ventana visible/en primer plano y `VBOX_MCP_ALLOW_MOUSE` activo. Acepta nombre o UUID de la VM.

## Instalación rápida (Windows)

Doble clic en `install.cmd`, o desde PowerShell (ajusta la ruta):

```powershell
cd C:\ruta\a\vbox-mcp
.\install.cmd
```

El instalador:

- Detecta Python 3.11+ y crea/reutiliza `.venv`.
- Instala `vbox-mcp` en modo editable.
- Detecta `VBoxManage` y avisa si no lo encuentra (no instala VirtualBox).
- Hace backup de la config global de OpenCode y registra `vbox` automáticamente.
- Ejecuta un smoke test que lista tus VMs.

Opciones útiles:

```powershell
.\install.cmd -DryRun          # muestra lo que haría, sin cambios
.\install.cmd -SkipSmokeTest   # omite el listado de VMs
.\install.cmd -PythonPath "C:\Python312\python.exe"
```

Los backups quedan como `opencode.jsonc.bak-AAAAMMDD-HHMMSS-fff` junto a la config.

Instalación manual:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e .
```

### Desinstalar

```powershell
.\uninstall.cmd                  # pide confirmación
.\uninstall.cmd -DryRun          # muestra lo que haría, sin cambios
.\uninstall.cmd -KeepVenv -Yes   # quita el registro y conserva .venv
.\uninstall.cmd -PurgeData -Yes  # borra también auditoría y screenshots
```

El desinstalador hace backup de la config, elimina el registro `vbox` de OpenCode y `.venv`; conserva el log de auditoría salvo que uses `-PurgeData`. **No toca VirtualBox ni tus VMs, y conserva el resto del repositorio.**

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

Las operaciones largas (`vbox_clone_vm`, `vbox_delete_vm`, `vbox_snapshot_take`, `vbox_snapshot_restore`, `vbox_snapshot_delete`, `vbox_guest_copy_to` y `vbox_guest_copy_from`) aceptan `timeout_seconds` (600 por defecto, entre 1 y 3600). El resto usa `VBOX_MCP_TIMEOUT_SECONDS`.

## Tools

### Lectura (siempre disponibles)

| Tool | Qué hace |
|---|---|
| `vbox_list_vms` | Lista VMs y estado (`running`/`stopped`). Incluye `group` y `description`. |
| `vbox_vm_info` | Configuración y estado de una VM. Con `extended=true` incluye discos, NAT, carpetas compartidas. |
| `vbox_list_ostypes` | Tipos de SO válidos para crear VMs. |
| `vbox_snapshot_list` | Snapshots de una VM. |
| `vbox_list_networks` | Interfaces host-only y redes NAT. |
| `vbox_guest_ip` | IPv4 reportada por Guest Additions. Con `all_nics=true` devuelve todas las NICs. |
| `vbox_screenshot` | PNG de la pantalla de la VM. Con `output_path` guarda en archivo. |
| `vbox_host_info` | Info del host: CPUs, RAM, SO, extensiones de virtualización. |
| `vbox_list_groups` | Lista los grupos de VMs configurados. |
| `vbox_list_media` | Lista todos los medios registrados (discos, ISOs, floppy). |
| `vbox_disk_info` | Info de un medio: tamaño, formato, UUID, estado. |
| `vbox_audit_log` | Lee el audit log del servidor (últimas N entradas). |
| `vbox_audit_stats` | Estadísticas del audit log: llamadas por tool, errores, duración media. |
| `vbox_wait_for_state` | Espera a que una VM alcance un estado (`running`, `stopped`, `paused`, `saved`). |
| `vbox_nat_list_rules` | Lista todas las reglas NAT de una VM. |

### Ciclo de vida

`vbox_start_vm`, `vbox_stop_vm`, `vbox_pause_vm`, `vbox_resume_vm`, `vbox_reset_vm`, `vbox_create_vm`, `vbox_modify_vm`, `vbox_clone_vm`, `vbox_delete_vm`.

### Almacenamiento y red

`vbox_attach_iso`, `vbox_detach_iso`, `vbox_shared_folder_add`, `vbox_shared_folder_remove`, `vbox_nat_port_forward_add`, `vbox_nat_port_forward_remove`, `vbox_vrde_configure`.

### Discos

`vbox_disk_create`, `vbox_disk_attach`, `vbox_disk_detach`, `vbox_disk_resize`, `vbox_disk_info`, `vbox_list_media`.

### Snapshots

`vbox_snapshot_take`, `vbox_snapshot_restore`, `vbox_snapshot_delete`, `vbox_snapshot_rename`, `vbox_snapshot_list`.

### Exportar/Importar

`vbox_export_vm`, `vbox_import_vm`.

### Guest control (Guest Additions)

`vbox_guest_exec`, `vbox_guest_run_script`, `vbox_guest_copy_to`, `vbox_guest_copy_from`.

### GUI

`vbox_send_keys`, `vbox_mouse_move`, `vbox_mouse_click`.

### Agrupación

`vbox_group_vms`.

Total: **43 tools**.

## Recursos MCP

| Recurso | Qué hace |
|---|---|
| `vbox://health` | Health check del servidor y VirtualBox. |
| `vbox://version` | Información de versión del servidor y VBoxManage. |
| `vbox://host` | Información del host (CPUs, RAM, SO). |

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
- En VMs encendidas o pausadas las reglas NAT se aplican en caliente y se guardan en la configuración (siguen activas tras reiniciar). Las carpetas compartidas añadidas en caliente son `transient` y desaparecen al apagar la VM; las persistentes se gestionan con la VM apagada.
- `vbox_clone_vm(mode="linked")` requiere `snapshot` (VirtualBox solo enlaza desde un snapshot); `mode="full"` copia el disco sin snapshots.
- `vbox_guest_exec` devuelve el `exit_code` real del guest aunque sea distinto de cero (VBoxManage desplaza 1..93 a 33..125). Si el guest sale con 94 o más, VBoxManage solo informa 126: la tool devuelve `exit_code: null` y un `note` explicativo. Si VBoxManage falla antes de ejecutar (timeout, Guest Additions, credenciales), la tool devuelve `isError`.
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

- El ratón solo funciona en Windows: mueve el cursor real sobre la ventana de VirtualBox. No uses la máquina mientras un agente controle el ratón. La ventana debe estar visible y en primer plano; si otra ventana tiene el foco, la tool falla en vez de enviar clics a ciegas.
- `vbox_screenshot`, `vbox_send_keys` y `vbox_mouse_*` requieren la VM encendida (no sirven en estado guardado).
- Sin Guest Additions, `vbox_guest_*` y las carpetas compartidas fallan con un mensaje accionable.
- Las carpetas compartidas añadidas con la VM encendida son `--transient` (VirtualBox no permite persistirlas en caliente); vuelven a desaparecer al apagar la VM.
- El servidor no instala Guest Additions ni crea controladores SATA en VMs ya existentes; `vbox_create_vm` sí lo hace.

## Troubleshooting

### VBoxManage no encontrado
```
Error: No se encontró VBoxManage. Define VBOX_MANAGE_PATH o instala VirtualBox.
```
- Verifica que VirtualBox esté instalado.
- En Windows, la ruta típica es `C:\Program Files\Oracle\VirtualBox\VBoxManage.exe`.
- Define `VBOX_MANAGE_PATH` en las variables de entorno si está en otra ubicación.

### Guest Additions no disponibles
```
Error: Guest Additions no están instaladas o su servicio no está en ejecución en la VM.
```
- Instala las Guest Additions en la VM (Dispositivos → Insertar imagen de CD de las «Guest Additions»).
- Reinicia la VM después de la instalación.
- Verifica que el servicio `VBoxService` (Linux) o `VBoxService.exe` (Windows) esté corriendo.

### Credenciales de guest incorrectas
```
Error: Credenciales del guest incorrectas: revisa usuario y contraseña.
```
- Verifica el usuario y contraseña dentro de la VM.
- En Linux, el usuario suele ser tu usuario normal (no root).
- En Windows, usa el nombre de usuario completo (ej. `Usuario` o `Administrador`).

### Timeout en operaciones largas
```
Error: VBoxManage excedió el timeout de 60 s ejecutando: clonevm ...
```
- Las operaciones como `vbox_clone_vm`, `vbox_export_vm`, `vbox_import_vm`, `vbox_snapshot_*` aceptan `timeout_seconds` (máx. 3600).
- Aumenta `VBOX_MCP_TIMEOUT_SECONDS` para timeouts globales.

### Ratón no funciona
- Solo funciona en Windows.
- La VM debe estar en modo `gui` (no `headless`).
- La ventana de VirtualBox debe estar visible y en primer plano.
- `VBOX_MCP_ALLOW_MOUSE` debe ser `true` (es el default).

### Nombre de VM bloqueado por patrón peligroso
```
Error: Nombre de VM coincide con patrón peligroso: *test*
```
- Revisa `VBOX_MCP_DANGEROUS_VM_PATTERNS` (lista de patrones separados por comas).
- Patrones usan sintaxis fnmatch (`*`, `?`, `[seq]`, `[!seq]`).

### Modo solo lectura
```
Error: El servidor está en modo solo lectura (VBOX_MCP_READONLY=true); esta operación no está permitida.
```
- Pon `VBOX_MCP_READONLY=false` o elimina la variable para permitir operaciones de escritura.

### Confirmación requerida
```json
{
  "status": "confirmation_required",
  "action": "delete",
  "target": "MiVM",
  "effects": ["se desregistra la VM", "se borran sus discos del host"]
}
```
- Reenvía la llamada con `confirm=true` para ejecutar la operación destructiva.

## Changelog

### v0.2.0 (2026-10-22)
- **Nuevas tools (12):** `vbox_disk_create`, `vbox_disk_attach`, `vbox_disk_detach`, `vbox_disk_resize`, `vbox_disk_info`, `vbox_list_media`, `vbox_export_vm`, `vbox_import_vm`, `vbox_guest_run_script`, `vbox_wait_for_state`, `vbox_audit_log`, `vbox_audit_stats`, `vbox_host_info`, `vbox_list_groups`, `vbox_snapshot_rename`, `vbox_nat_list_rules`, `vbox_vrde_configure`, `vbox_group_vms`.
- **Mejoras a tools existentes:** `vbox_list_vms` incluye `group` y `description`; `vbox_vm_info` modo `extended` con discos, NAT, carpetas compartidas; `vbox_modify_vm` soporta `vram_mb`, `boot_order`, `description`; `vbox_start_vm` modo `separate`; `vbox_guest_exec` soporta `stdin`; `vbox_screenshot` guarda en `output_path`.
- **MCP Resources:** `vbox://health`, `vbox://version`, `vbox://host`.
- **Seguridad:** Bloqueo de nombres de VM con patrones peligrosos (`VBOX_MCP_DANGEROUS_VM_PATTERNS`).
- **Observabilidad:** Audit log con estadísticas (`vbox_audit_stats`).
- **Tests:** Añadidos `test_disks.py` y `test_export.py` (28 tests nuevos).
- **Config:** `max_retries` (`VBOX_MCP_RETRIES`), `rate_limit` (`VBOX_MCP_RATE_LIMIT`).

### v0.1.0
- Versión inicial con ciclo de vida básico, snapshots, ISOs, carpetas compartidas, NAT, guest control y GUI.
