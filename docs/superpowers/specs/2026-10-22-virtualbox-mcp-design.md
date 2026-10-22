# vbox-mcp — Servidor MCP para VirtualBox

Fecha: 2026-10-22
Estado: aprobado para planificación

## 1. Propósito

Exponer el control de VirtualBox a OpenCode mediante el Model Context Protocol
(transporte stdio), para que un agente pueda inspeccionar, arrancar, parar,
clonar, snapshottear y operar máquinas virtuales locales, incluyendo ejecución
de comandos dentro del guest y control visual (screenshot, teclado y ratón).

Éxito significa:

- `opencode mcp list` muestra el servidor conectado.
- El agente lista las VMs registradas y obtiene información estructurada.
- El agente puede capturar la pantalla de una VM encendida y enviar teclado.
- Ninguna operación destructiva se ejecuta sin `confirm=true`.
- Los tests unitarios corren sin VirtualBox real.

## 2. Contexto y restricciones

- Host de desarrollo: Windows, VirtualBox 7.2.20 en
  `C:\Program Files\Oracle\VirtualBox\VBoxManage.exe` (no está en PATH).
- Python 3.14 disponible. PyPI accesible. npm registry y releases de GitHub
  bloqueados en este entorno.
- Se usa el SDK oficial `mcp` de PyPI y `VBoxManage` como única interfaz con
  VirtualBox.
- VirtualBox no expone eventos de ratón por CLI; se resuelven con
  automatización de la ventana en Windows.
- No se soportan Hyper-V, Vagrant, VirtualBox remoto ni el SOAP de
  `vboxwebsrv` en esta versión.

## 3. Arquitectura

Proyecto independiente en `C:\Users\Usuario\vbox-mcp`, con git propio.

```
vbox-mcp/
├── pyproject.toml
├── README.md
├── src/vbox_mcp/
│   ├── __init__.py
│   ├── __main__.py        # arranque stdio
│   ├── config.py          # env vars, rutas, detección de VBoxManage
│   ├── vboxmanage.py      # ejecución y parseo de VBoxManage
│   ├── gui.py             # screenshot, teclado, ratón Win32
│   ├── safety.py          # confirmaciones, audit log, redacción
│   ├── models.py          # esquemas Pydantic de entrada/salida
│   └── server.py          # definición de tools MCP
├── tests/
│   ├── fake_vboxmanage.py
│   ├── conftest.py
│   └── test_*.py
└── scripts/install.ps1
```

Principios:

- `vboxmanage.py` es el único módulo que lanza procesos. Usa listas de
  argumentos, nunca `shell=True`, con timeout y captura de stdout/stderr.
- `server.py` no conoce detalles de CLI: valida con Pydantic, llama a la capa
  correspondiente y devuelve resultados estructurados.
- `gui.py` aísla todo el código específico de Windows detrás de funciones
  puras (mapeo de coordenadas) y una capa fina de `ctypes`.
- Las credenciales de guest nunca aparecen en `argv` ni en logs.

## 4. Configuración

Variables de entorno:

| Variable | Defecto | Uso |
|---|---|---|
| `VBOX_MANAGE_PATH` | autodetección | Ruta a `VBoxManage.exe` |
| `VBOX_MCP_READONLY` | `false` | Desactiva todas las tools mutantes |
| `VBOX_MCP_TIMEOUT_SECONDS` | `60` | Timeout por comando |
| `VBOX_MCP_AUDIT_LOG` | `%LOCALAPPDATA%\vbox-mcp\audit.log` | JSONL de auditoría |
| `VBOX_MCP_ALLOW_MOUSE` | `true` en Windows | Habilita tools de ratón |
| `VBOX_MCP_GUEST_USER` | vacío | Usuario guest por defecto |
| `VBOX_MCP_GUEST_PASSWORD` | vacío | Password guest por defecto |

Detección de `VBoxManage`, en orden: variable de entorno, `PATH`, rutas
estándar de Windows/Linux/macOS. Si no se encuentra, el servidor arranca pero
las tools devuelven un error explicativo (no rompe `initialize`).

## 5. Tools

Identificador común `vm`: nombre o UUID. La capa de ejecución resuelve y
valida antes de invocar.

### Lectura (siempre disponibles)

| Tool | Entrada | Salida |
|---|---|---|
| `vbox_list_vms` | `running_only: bool = false` | lista `{name, uuid, state}` |
| `vbox_vm_info` | `vm` | resumen + mapa `showvminfo --machinereadable` |
| `vbox_list_ostypes` | — | `{id, description, family}` |
| `vbox_snapshot_list` | `vm` | `{name, uuid, description, current}` |
| `vbox_list_networks` | — | host-only interfaces y NAT networks |
| `vbox_guest_ip` | `vm` | IPv4 reportada por Guest Additions |
| `vbox_screenshot` | `vm`, `display: int = 0` | imagen PNG + ruta guardada |

### Ciclo de vida

| Tool | Entrada | Notas |
|---|---|---|
| `vbox_start_vm` | `vm`, `mode: "headless"\|"gui"` | GUI necesario para ratón |
| `vbox_stop_vm` | `vm`, `mode: "acpi"\|"poweroff"\|"save"` | `poweroff` exige `confirm` |
| `vbox_pause_vm` | `vm` | |
| `vbox_resume_vm` | `vm` | |
| `vbox_reset_vm` | `vm`, `confirm` | destructivo |
| `vbox_create_vm` | `name`, `ostype`, `cpus=2`, `memory_mb=2048`, `disk_mb=0`, `iso=None`, `network="nat"` | registra la VM |
| `vbox_modify_vm` | `vm`, `cpus`, `memory_mb`, `nic` | whitelist de campos |
| `vbox_clone_vm` | `source`, `name`, `mode="full"\|"linked"`, `snapshot=None` | |
| `vbox_delete_vm` | `vm`, `delete_disks=false`, `confirm` | destructivo |

### Almacenamiento y red

| Tool | Entrada |
|---|---|
| `vbox_attach_iso` | `vm`, `iso_path`, `controller="sata"`, `port=1` |
| `vbox_detach_iso` | `vm`, `controller="sata"`, `port=1` |
| `vbox_shared_folder_add` | `vm`, `name`, `host_path`, `automount=true`, `readonly=false` |
| `vbox_shared_folder_remove` | `vm`, `name` |
| `vbox_nat_port_forward_add` | `vm`, `rule_name`, `protocol`, `host_port`, `guest_port`, `guest_ip=""` |
| `vbox_nat_port_forward_remove` | `vm`, `rule_name` |

### Snapshots

| Tool | Entrada | Notas |
|---|---|---|
| `vbox_snapshot_take` | `vm`, `name`, `description=""` | |
| `vbox_snapshot_restore` | `vm`, `name`, `confirm` | destructivo |
| `vbox_snapshot_delete` | `vm`, `name`, `confirm` | destructivo |

### Guest (requiere Guest Additions)

| Tool | Entrada | Salida |
|---|---|---|
| `vbox_guest_exec` | `vm`, `user`, `password`, `exe`, `args=[]`, `timeout=60`, `env={}`, `working_dir=None` | `{exit_code, stdout, stderr}` |
| `vbox_guest_copy_to` | `vm`, `user`, `password`, `host_path`, `guest_path` | estado |
| `vbox_guest_copy_from` | `vm`, `user`, `password`, `guest_path`, `host_path` | estado |

### GUI

| Tool | Entrada | Notas |
|---|---|---|
| `vbox_send_keys` | `vm`, `text`, `delay_ms=50`, `method="string"\|"scancode"` | soporta tokens `<enter>`, `<esc>`, `<tab>`, `<f2>`, `<down>`… |
| `vbox_mouse_move` | `vm`, `x`, `y` | Windows, VM en modo GUI |
| `vbox_mouse_click` | `vm`, `x`, `y`, `button="left"`, `double=false` | Windows, VM en modo GUI |

## 6. Seguridad

- `VBOX_MCP_READONLY=true` elimina del catálogo las tools mutantes.
- Tools destructivas exigen `confirm=true`. Sin él devuelven
  `{status: "confirmation_required", action, target, effects}` sin ejecutar.
- `vbox_delete_vm` no borra discos salvo `delete_disks=true`.
- Las contraseñas de guest se escriben en un archivo temporal con permisos
  restringidos, se pasan con `--passwordfile` y se eliminan en `finally`.
- El audit log JSONL registra tool, argumentos redactados, resultado y
  duración. Nunca registra contraseñas.
- Límite de tamaño en salidas de comandos (por defecto 1 MB) para no inundar
  el contexto del agente.

## 7. Estrategia GUI

- **Screenshot:** `VBoxManage controlvm <vm> screenshotpng <tmp> [display]`.
  Se devuelve `ImageContent` PNG y la ruta del archivo.
- **Teclado:** `keyboardputstring` para texto ASCII; `keyboardputscancode` para
  tokens especiales, con mapa de scancodes US.
- **Ratón:** solo Windows y VM en modo GUI. Se localiza la ventana
  `<nombre> [Running] - Oracle VirtualBox`, se valida que esté en primer plano,
  se mapean coordenadas del framebuffer (dimensiones del screenshot) al área
  cliente con `GetClientRect`/`ClientToScreen` y se emiten eventos con
  `SetCursorPos` + `mouse_event`. Si la ventana no existe, error claro
  indicando arrancar con `mode="gui"`.
- El mapeo de coordenadas es una función pura testeable sin Windows.

## 8. Testing

- **Unitarios:** `tests/fake_vboxmanage.py` es un ejecutable Python que
  registra `argv` en JSON y devuelve respuestas configurables.
  Cubre: parseo de `list vms`, `showvminfo --machinereadable`, snapshots,
  construcción de argumentos, modo readonly, puerta de confirmación,
  redacción de secretos, mapa de scancodes y mapeo de coordenadas.
- **Integración de solo lectura:** contra VirtualBox real, lista VMs e info de
  una VM. Screenshot solo si hay una VM encendida. Nunca muta.
- **Mutación opcional:** con `VBOX_MCP_MUTATION_TESTS=1`, crea una VM vacía sin
  disco y la desregistra. No se ejecuta por defecto.
- Cobertura objetivo de la lógica propia: >80 %.

## 9. Integración con OpenCode

Se documenta el snippet stdio:

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

La forma exacta se valida contra la documentación V2 de OpenCode durante la
implementación y se verifica con `opencode mcp list`.

## 10. Fuera de alcance

- Hyper-V, Vagrant, VMware, Proxmox.
- VirtualBox remoto o `vboxwebsrv`/SOAP.
- Interfaz web o TUI propia.
- Instalación desatendida de sistemas operativos.
- Soporte de ratón fuera de Windows.

## 11. Riesgos

| Riesgo | Mitigación |
|---|---|
| `VBoxManage` cambia formato de salida | Parseo defensivo + tests con salidas reales |
| Permisos/antivirus al lanzar procesos | Rutas absolutas, sin shell, errores claros |
| Automatización de ratón frágil | Solo GUI, validación de ventana, función pura testeada |
| Guest Additions ausentes | Error explícito con instrucción de instalación |
| Fuga de credenciales | `--passwordfile` temporal + redacción en logs |
