# Plan de mejoras — vbox-mcp Supreme

## Nuevas features a implementar

### 🆕 Nuevas tools MCP
1. **`vbox_disk_create`** — Crear un disco VDI/VMDK/VHD independiente
2. **`vbox_disk_attach`** — Adjuntar un disco existente a una VM
3. **`vbox_disk_detach`** — Desadjuntar un disco de una VM
4. **`vbox_disk_resize`** — Redimensionar un VDI en caliente
5. **`vbox_disk_info`** — Info de un medio (tamaño, formato, UUID)
6. **`vbox_export_vm`** — Exportar VM a OVA/OVF
7. **`vbox_import_vm`** — Importar OVA/OVF
8. **`vbox_guest_run_script`** — Enviar y ejecutar script de texto en el guest
9. **`vbox_wait_for_state`** — Esperar a que una VM alcance un estado
10. **`vbox_list_media`** — Listar todos los medios registrados
11. **`vbox_audit_log`** — Leer el audit log (últimas N entradas)
12. **`vbox_host_info`** — Info del host (CPUs, RAM, SO) desde VBoxManage
13. **`vbox_group_vms`** — Agrupar VMs en un grupo VirtualBox
14. **`vbox_snapshot_rename`** — Renombrar un snapshot existente
15. **`vbox_nat_list_rules`** — Listar reglas NAT de una VM
16. **`vbox_vrde_configure`** — Configurar VRDE/RDP de una VM

### 🔧 Mejoras a tools existentes
- `vbox_list_vms`: añadir campo `group` y `description`
- `vbox_vm_info`: añadir discos adjuntos, reglas NAT, carpetas compartidas
- `vbox_modify_vm`: añadir soporte para video RAM, boot order, description
- `vbox_start_vm`: añadir modo `separate`
- `vbox_guest_exec`: añadir `stdin` para pipear datos
- `vbox_screenshot`: guardar opcionalmente a ruta custom

### 🛡️ Mejoras de seguridad/robustez
- Rate limiting configurable por tool (VBOX_MCP_RATE_LIMIT)
- Bloqueo de nombres de VM con patrones peligrosos (configurable)
- Timeout individual por tool configurable via env vars
- Mejor manejo de encoding en parseo
- Retry automático en errores transitorios (VBOX_MCP_RETRIES)

### 📊 Observabilidad
- Métricas en el audit log (histograma de duración por tool)
- `vbox_audit_log` tool para leer el log desde el agente
- Health check endpoint (resource MCP)
- Version resource con info del servidor y VBoxManage

### 🧪 Tests
- Tests para cada nueva función
- Tests de error paths mejorados
- Tests de integración ampliados

### 📖 Documentación
- README mejorado con más ejemplos
- Tabla de todas las tools nueva
- Sección de troubleshooting
- Changelog

## Archivos a crear/modificar
- `src/vbox_mcp/disks.py` (nuevo)
- `src/vbox_mcp/export.py` (nuevo)
- `src/vbox_mcp/metrics.py` (nuevo)
- `src/vbox_mcp/resources.py` (nuevo)
- `src/vbox_mcp/server.py` (mejorado)
- `src/vbox_mcp/vboxmanage.py` (mejorado)
- `src/vbox_mcp/lifecycle.py` (mejorado)
- `src/vbox_mcp/storage.py` (mejorado)
- `src/vbox_mcp/config.py` (mejorado)
- `src/vbox_mcp/safety.py` (mejorado)
- `src/vbox_mcp/parsing.py` (mejorado)
- `src/vbox_mcp/guest.py` (mejorado)
- `tests/test_disks.py` (nuevo)
- `tests/test_export.py` (nuevo)
- `README.md` (reescrito)
