"""Definición de las tools MCP — vbox-mcp supreme."""

from __future__ import annotations

import time
from typing import Any, Callable

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import disks, export, guest, gui, lifecycle, metrics, snapshots, storage
from .config import Settings
from .resources import health_check, host_info_resource, version_info
from .safety import ConfirmationRequired, audit, ensure_writable, require_confirm
from .vboxmanage import (
    VBoxError,
    guest_ip,
    guest_ips,
    host_info,
    list_groups,
    list_networks,
    list_ostypes,
    list_vms,
    snapshot_list,
    vm_info,
    vm_info_extended,
    wait_for_state,
)


def _elapsed_ms(start: float) -> int:
    return int((time.perf_counter() - start) * 1000)


def _clamp_timeout(value: int) -> int:
    return min(3600, max(1, int(value)))


def _read(
    settings: Settings,
    tool: str,
    args: dict[str, Any],
    start: float,
    fn: Callable[[], Any],
) -> Any:
    try:
        value = fn()
    except (VBoxError, OSError) as exc:
        audit(settings, tool, args, f"error: {exc}", _elapsed_ms(start))
        raise ToolError(str(exc)) from exc
    audit(settings, tool, args, "ok", _elapsed_ms(start))
    return value


def _mutate(
    settings: Settings,
    tool: str,
    args: dict[str, Any],
    start: float,
    confirm: bool,
    action: str,
    target: str,
    effects: list[str],
    fn: Callable[[], Any],
) -> Any:
    try:
        ensure_writable(settings)
        require_confirm(confirm, action, target, effects)
    except ConfirmationRequired as exc:
        audit(
            settings,
            tool,
            args,
            "confirmation_required",
            _elapsed_ms(start),
        )
        return {
            "status": "confirmation_required",
            "action": exc.action,
            "target": exc.target,
            "effects": exc.effects,
        }
    except (VBoxError, OSError) as exc:
        audit(settings, tool, args, f"error: {exc}", _elapsed_ms(start))
        raise ToolError(str(exc)) from exc
    return _read(settings, tool, args, start, fn)


def build_server(settings: Settings | None = None) -> MCPServer:
    settings = settings or Settings.from_env()
    server = MCPServer(
        "vbox-mcp",
        version="0.2.0",
        instructions=(
            "Controla VirtualBox local mediante VBoxManage. "
            "Identifica las VMs por nombre o UUID. "
            "Las operaciones destructivas requieren confirm=true. "
            "Usa vbox_list_vms para ver las VMs disponibles, "
            "vbox_vm_info para detalles completos incluyendo discos y reglas NAT. "
            "Para Guest Additions: vbox_guest_exec, vbox_guest_copy_to/from, vbox_guest_run_script. "
            "Para snapshots: vbox_snapshot_take/restore/delete/rename. "
            "Para discos: vbox_disk_create/attach/detach/resize/info. "
            "Para exportar/importar: vbox_export_vm, vbox_import_vm."
        ),
    )

    # ----------------------------- Lectura -----------------------------

    @server.tool()
    def vbox_list_vms(running_only: bool = False) -> dict:
        """Lista las máquinas virtuales registradas y su estado (running/stopped).

        Args:
            running_only: Si es true, solo muestra las VMs que están encendidas.
        """
        start = time.perf_counter()
        args = {"running_only": running_only}
        return _read(
            settings,
            "vbox_list_vms",
            args,
            start,
            lambda: {"vms": list_vms(settings, running_only)},
        )

    @server.tool()
    def vbox_vm_info(vm: str, extended: bool = False) -> dict:
        """Muestra configuración y estado de una VM (CPU, RAM, discos, red, snapshots).

        Args:
            vm: Nombre o UUID de la VM.
            extended: Si es true, incluye discos adjuntos, reglas NAT y carpetas compartidas.
        """
        start = time.perf_counter()
        if extended:
            return _read(
                settings, "vbox_vm_info", {"vm": vm, "extended": True}, start,
                lambda: vm_info_extended(settings, vm)
            )
        return _read(settings, "vbox_vm_info", {"vm": vm}, start, lambda: vm_info(settings, vm))

    @server.tool()
    def vbox_list_ostypes() -> dict:
        """Lista los tipos de sistema operativo que entiende VirtualBox."""
        start = time.perf_counter()
        return _read(
            settings,
            "vbox_list_ostypes",
            {},
            start,
            lambda: {"ostypes": list_ostypes(settings)},
        )

    @server.tool()
    def vbox_snapshot_list(vm: str) -> dict:
        """Lista los snapshots de una VM con nombre, UUID, descripción y si es el actual.

        Args:
            vm: Nombre o UUID de la VM.
        """
        start = time.perf_counter()
        return _read(
            settings,
            "vbox_snapshot_list",
            {"vm": vm},
            start,
            lambda: {"snapshots": snapshot_list(settings, vm)},
        )

    @server.tool()
    def vbox_list_networks() -> dict:
        """Lista interfaces host-only y redes NAT del host."""
        start = time.perf_counter()
        return _read(settings, "vbox_list_networks", {}, start, lambda: list_networks(settings))

    @server.tool()
    def vbox_guest_ip(vm: str, all_nics: bool = False) -> dict:
        """Obtiene la IPv4 que reporta Guest Additions para una VM encendida.

        Args:
            vm: Nombre o UUID de la VM.
            all_nics: Si es true, devuelve IPs de todas las NICs (IPv4 e IPv6).
        """
        start = time.perf_counter()
        if all_nics:
            return _read(
                settings,
                "vbox_guest_ip",
                {"vm": vm, "all_nics": True},
                start,
                lambda: {"vm": vm, "ips": guest_ips(settings, vm)},
            )
        return _read(
            settings,
            "vbox_guest_ip",
            {"vm": vm},
            start,
            lambda: {"vm": vm, "ip": guest_ip(settings, vm)},
        )

    @server.tool()
    def vbox_screenshot(vm: str, display: int = 0, output_path: str = "") -> Image | dict:
        """Captura la pantalla de una VM encendida y devuelve el PNG o lo guarda en archivo.

        Args:
            vm: Nombre o UUID de la VM.
            display: Número de pantalla (0 = pantalla principal).
            output_path: Ruta opcional donde guardar el PNG. Si se omite, devuelve la imagen.
        """
        start = time.perf_counter()
        try:
            path = gui.screenshot(settings, vm, display, output_path=output_path or None)
            if output_path:
                audit(
                    settings,
                    "vbox_screenshot",
                    {"vm": vm, "display": display, "output_path": output_path},
                    "ok",
                    _elapsed_ms(start),
                )
                return {"vm": vm, "action": "screenshot", "output_path": output_path}
            try:
                data = path.read_bytes()
            finally:
                path.unlink(missing_ok=True)
        except (OSError, VBoxError) as exc:
            audit(
                settings,
                "vbox_screenshot",
                {"vm": vm, "display": display, "output_path": output_path},
                f"error: {exc}",
                _elapsed_ms(start),
            )
            raise ToolError(str(exc)) from exc
        audit(
            settings,
            "vbox_screenshot",
            {"vm": vm, "display": display},
            "ok",
            _elapsed_ms(start),
        )
        return Image(data=data, format="png")

    @server.tool()
    def vbox_host_info() -> dict:
        """Devuelve información del host: CPUs, RAM, SO, extensiones de virtualización."""
        start = time.perf_counter()
        return _read(settings, "vbox_host_info", {}, start, lambda: host_info(settings))

    @server.tool()
    def vbox_list_groups() -> dict:
        """Lista los grupos de VMs configurados en VirtualBox."""
        start = time.perf_counter()
        return _read(settings, "vbox_list_groups", {}, start, lambda: list_groups(settings))

    @server.tool()
    def vbox_list_media(media_type: str = "disk") -> dict:
        """Lista todos los medios (discos, ISOs, floppy) registrados en VirtualBox.

        Args:
            media_type: Tipo de medio: 'disk', 'dvd' o 'floppy'.
        """
        start = time.perf_counter()
        return _read(
            settings,
            "vbox_list_media",
            {"media_type": media_type},
            start,
            lambda: disks.list_media(settings, media_type),
        )

    @server.tool()
    def vbox_disk_info(disk_path: str) -> dict:
        """Obtiene información de un disco o ISO: tamaño, formato, UUID, estado.

        Args:
            disk_path: Ruta al archivo de disco o UUID.
        """
        start = time.perf_counter()
        return _read(
            settings,
            "vbox_disk_info",
            {"disk_path": disk_path},
            start,
            lambda: disks.disk_info(settings, disk_path),
        )

    @server.tool()
    def vbox_audit_log(
        last_n: int = 50,
        tool_filter: str = "",
        result_filter: str = "",
    ) -> dict:
        """Lee el audit log del servidor MCP (últimas N entradas).

        Args:
            last_n: Número de entradas a mostrar (máx. 1000).
            tool_filter: Si se indica, filtra por nombre de tool exacto.
            result_filter: Si se indica, filtra por resultado ('ok', 'error', etc.).
        """
        start = time.perf_counter()
        return _read(
            settings,
            "vbox_audit_log",
            {"last_n": last_n, "tool_filter": tool_filter},
            start,
            lambda: metrics.read_audit_log(settings, last_n, tool_filter, result_filter),
        )

    @server.tool()
    def vbox_audit_stats() -> dict:
        """Devuelve estadísticas del audit log: llamadas por tool, errores y duración media."""
        start = time.perf_counter()
        return _read(
            settings,
            "vbox_audit_stats",
            {},
            start,
            lambda: metrics.audit_stats(settings),
        )

    @server.tool()
    def vbox_wait_for_state(
        vm: str,
        target_state: str,
        timeout_seconds: int = 120,
    ) -> dict:
        """Espera hasta que la VM alcance el estado indicado.

        Args:
            vm: Nombre o UUID de la VM.
            target_state: Estado a esperar: 'running', 'stopped', 'paused', 'saved', 'aborted'.
            timeout_seconds: Segundos máximos de espera (máx. 3600).
        """
        start = time.perf_counter()
        return _read(
            settings,
            "vbox_wait_for_state",
            {"vm": vm, "target_state": target_state},
            start,
            lambda: wait_for_state(settings, vm, target_state, _clamp_timeout(timeout_seconds)),
        )

    @server.tool()
    def vbox_nat_list_rules(vm: str) -> dict:
        """Lista todas las reglas de reenvío de puertos NAT de una VM.

        Args:
            vm: Nombre o UUID de la VM.
        """
        start = time.perf_counter()
        return _read(
            settings,
            "vbox_nat_list_rules",
            {"vm": vm},
            start,
            lambda: storage.nat_list_rules(settings, vm),
        )

    if not settings.readonly:
        # ------------------------- Ciclo de vida -------------------------

        @server.tool()
        def vbox_start_vm(vm: str, mode: str = "headless") -> dict:
            """Arranca una VM.

            Args:
                vm: Nombre o UUID de la VM.
                mode: 'headless' (sin ventana), 'gui' (con ventana, necesario para ratón)
                      o 'separate' (proceso separado del frontend).
            """
            start = time.perf_counter()
            args = {"vm": vm, "mode": mode}
            return _mutate(
                settings,
                "vbox_start_vm",
                args,
                start,
                True,
                "start",
                vm,
                [],
                lambda: lifecycle.start_vm(settings, vm, mode),
            )

        @server.tool()
        def vbox_stop_vm(vm: str, mode: str = "acpi", confirm: bool = False) -> dict:
            """Apaga una VM.

            Args:
                vm: Nombre o UUID de la VM.
                mode: 'acpi' (botón de apagado suave), 'save' (guarda estado) o
                      'poweroff' (corte de corriente; requiere confirm=true).
                confirm: Requerido para mode='poweroff'.
            """
            start = time.perf_counter()
            args = {"vm": vm, "mode": mode, "confirm": confirm}
            effects = (
                ["se pierde el estado no guardado de la VM"]
                if mode == "poweroff"
                else []
            )
            return _mutate(
                settings,
                "vbox_stop_vm",
                args,
                start,
                confirm or mode != "poweroff",
                "stop",
                vm,
                effects,
                lambda: lifecycle.stop_vm(settings, vm, mode),
            )

        @server.tool()
        def vbox_pause_vm(vm: str) -> dict:
            """Pausa una VM en ejecución (congela la CPU sin apagar).

            Args:
                vm: Nombre o UUID de la VM.
            """
            start = time.perf_counter()
            return _mutate(
                settings,
                "vbox_pause_vm",
                {"vm": vm},
                start,
                True,
                "pause",
                vm,
                [],
                lambda: lifecycle.pause_vm(settings, vm),
            )

        @server.tool()
        def vbox_resume_vm(vm: str) -> dict:
            """Reanuda una VM pausada.

            Args:
                vm: Nombre o UUID de la VM.
            """
            start = time.perf_counter()
            return _mutate(
                settings,
                "vbox_resume_vm",
                {"vm": vm},
                start,
                True,
                "resume",
                vm,
                [],
                lambda: lifecycle.resume_vm(settings, vm),
            )

        @server.tool()
        def vbox_reset_vm(vm: str, confirm: bool = False) -> dict:
            """Reinicia una VM a lo bruto (equivale a pulsar Reset; requiere confirm=true).

            Args:
                vm: Nombre o UUID de la VM.
                confirm: Debe ser true para ejecutar el reinicio forzado.
            """
            start = time.perf_counter()
            return _mutate(
                settings,
                "vbox_reset_vm",
                {"vm": vm, "confirm": confirm},
                start,
                confirm,
                "reset",
                vm,
                ["reinicio duro: se pierde el estado no guardado"],
                lambda: lifecycle.reset_vm(settings, vm),
            )

        @server.tool()
        def vbox_create_vm(
            name: str,
            ostype: str,
            cpus: int = 2,
            memory_mb: int = 2048,
            disk_mb: int = 0,
            iso: str = "",
            network: str = "nat",
            adapter: str = "",
        ) -> dict:
            """Crea y registra una VM nueva en VirtualBox.

            Args:
                name: Nombre de la nueva VM.
                ostype: Tipo de SO (obtenlo con vbox_list_ostypes).
                cpus: Número de vCPUs (mínimo 1).
                memory_mb: RAM en MiB (mínimo 128).
                disk_mb: Tamaño del disco VDI en MiB (0 = no crear disco).
                iso: Ruta al ISO a montar en la unidad óptica (opcional).
                network: Tipo de red: 'nat', 'bridged', 'hostonly' o 'none'.
                adapter: Nombre del adaptador del host (requerido para bridged/hostonly).
            """
            start = time.perf_counter()
            args = {
                "name": name,
                "ostype": ostype,
                "cpus": cpus,
                "memory_mb": memory_mb,
                "disk_mb": disk_mb,
                "iso": iso,
                "network": network,
                "adapter": adapter,
            }
            return _mutate(
                settings,
                "vbox_create_vm",
                args,
                start,
                True,
                "create",
                name,
                [],
                lambda: lifecycle.create_vm(
                    settings,
                    name,
                    ostype,
                    cpus=cpus,
                    memory_mb=memory_mb,
                    disk_mb=disk_mb,
                    iso=iso or None,
                    network=network,
                    adapter=adapter,
                ),
            )

        @server.tool()
        def vbox_modify_vm(
            vm: str,
            cpus: int | None = None,
            memory_mb: int | None = None,
            vram_mb: int | None = None,
            nic: str | None = None,
            adapter: str = "",
            description: str | None = None,
            boot_order: list[str] | None = None,
        ) -> dict:
            """Modifica la configuración de una VM (debe estar apagada para cambios de hardware).

            Args:
                vm: Nombre o UUID de la VM.
                cpus: Número de vCPUs.
                memory_mb: RAM en MiB.
                vram_mb: Memoria de video en MiB (1-256).
                nic: Modo de red para NIC1: 'nat', 'bridged', 'hostonly', 'none',
                     'intnet' o 'natnetwork'.
                adapter: Adaptador del host (requerido para bridged/hostonly).
                description: Descripción de la VM.
                boot_order: Orden de arranque, lista de hasta 4 elementos:
                            'disk', 'dvd', 'net', 'none'.
            """
            start = time.perf_counter()
            args = {
                "vm": vm,
                "cpus": cpus,
                "memory_mb": memory_mb,
                "vram_mb": vram_mb,
                "nic": nic,
                "adapter": adapter,
                "description": description,
                "boot_order": boot_order,
            }
            return _mutate(
                settings,
                "vbox_modify_vm",
                args,
                start,
                True,
                "modify",
                vm,
                [],
                lambda: lifecycle.modify_vm(
                    settings,
                    vm,
                    cpus=cpus,
                    memory_mb=memory_mb,
                    vram_mb=vram_mb,
                    nic=nic,
                    adapter=adapter or None,
                    description=description,
                    boot_order=boot_order,
                ),
            )

        @server.tool()
        def vbox_clone_vm(
            source: str,
            name: str,
            mode: str = "full",
            snapshot: str = "",
            timeout_seconds: int = 600,
        ) -> dict:
            """Clona una VM existente.

            Args:
                source: Nombre o UUID de la VM origen.
                name: Nombre del clon.
                mode: 'full' (copia completa del disco) o 'linked' (disco enlazado, más rápido
                      pero requiere que la VM origen siga existiendo; requiere snapshot).
                snapshot: Nombre del snapshot de origen (obligatorio para mode='linked').
                timeout_seconds: Tiempo máximo de espera (1-3600 s).
            """
            start = time.perf_counter()
            args = {
                "source": source,
                "name": name,
                "mode": mode,
                "snapshot": snapshot,
                "timeout_seconds": _clamp_timeout(timeout_seconds),
            }
            return _mutate(
                settings,
                "vbox_clone_vm",
                args,
                start,
                True,
                "clone",
                name,
                [],
                lambda: lifecycle.clone_vm(
                    settings,
                    source,
                    name,
                    mode=mode,
                    snapshot=snapshot or None,
                    timeout=_clamp_timeout(timeout_seconds),
                ),
            )

        @server.tool()
        def vbox_delete_vm(
            vm: str,
            delete_disks: bool = False,
            confirm: bool = False,
            timeout_seconds: int = 600,
        ) -> dict:
            """Desregistra una VM de VirtualBox. Requiere confirm=true.

            Args:
                vm: Nombre o UUID de la VM.
                delete_disks: Si es true, también borra los discos adjuntos del host.
                confirm: Debe ser true para ejecutar la eliminación.
                timeout_seconds: Tiempo máximo de espera (1-3600 s).
            """
            start = time.perf_counter()
            args = {
                "vm": vm,
                "delete_disks": delete_disks,
                "confirm": confirm,
                "timeout_seconds": _clamp_timeout(timeout_seconds),
            }
            effects = ["se desregistra la VM"]
            if delete_disks:
                effects.append("se borran sus discos del host")
            return _mutate(
                settings,
                "vbox_delete_vm",
                args,
                start,
                confirm,
                "delete",
                vm,
                effects,
                lambda: lifecycle.delete_vm(
                    settings,
                    vm,
                    delete_disks=delete_disks,
                    timeout=_clamp_timeout(timeout_seconds),
                ),
            )

        @server.tool()
        def vbox_group_vms(vms: list[str], group: str) -> dict:
            """Asigna una o más VMs a un grupo VirtualBox.

            Args:
                vms: Lista de nombres o UUIDs de VMs.
                group: Nombre del grupo (p.ej. 'Produccion' o '/Dev/Linux').
            """
            start = time.perf_counter()
            args = {"vms": vms, "group": group}
            return _mutate(
                settings,
                "vbox_group_vms",
                args,
                start,
                True,
                "group_vms",
                group,
                [],
                lambda: lifecycle.group_vms(settings, vms, group),
            )

        # --------------------- Almacenamiento y red ---------------------

        @server.tool()
        def vbox_attach_iso(
            vm: str,
            iso_path: str,
            controller: str = "sata",
            port: int = 1,
        ) -> dict:
            """Conecta un ISO a la unidad óptica de una VM.

            Args:
                vm: Nombre o UUID de la VM.
                iso_path: Ruta al archivo ISO en el host.
                controller: Nombre del controlador de almacenamiento ('sata', 'ide').
                port: Puerto del controlador (1 por defecto para la óptica).
            """
            start = time.perf_counter()
            args = {
                "vm": vm,
                "iso_path": iso_path,
                "controller": controller,
                "port": port,
            }
            return _mutate(
                settings,
                "vbox_attach_iso",
                args,
                start,
                True,
                "attach_iso",
                vm,
                [],
                lambda: storage.attach_iso(settings, vm, iso_path, controller=controller, port=port),
            )

        @server.tool()
        def vbox_detach_iso(vm: str, controller: str = "sata", port: int = 1) -> dict:
            """Desconecta el ISO de la unidad óptica de una VM.

            Args:
                vm: Nombre o UUID de la VM.
                controller: Nombre del controlador de almacenamiento.
                port: Puerto del controlador.
            """
            start = time.perf_counter()
            args = {"vm": vm, "controller": controller, "port": port}
            return _mutate(
                settings,
                "vbox_detach_iso",
                args,
                start,
                True,
                "detach_iso",
                vm,
                [],
                lambda: storage.detach_iso(settings, vm, controller=controller, port=port),
            )

        @server.tool()
        def vbox_shared_folder_add(
            vm: str,
            name: str,
            host_path: str,
            automount: bool = True,
            readonly: bool = False,
        ) -> dict:
            """Comparte una carpeta del host con la VM (requiere Guest Additions).

            Args:
                vm: Nombre o UUID de la VM.
                name: Nombre de la carpeta compartida dentro del guest.
                host_path: Ruta de la carpeta en el host.
                automount: Si es true, se monta automáticamente en el guest al arrancar.
                readonly: Si es true, el guest solo tiene acceso de lectura.
            """
            start = time.perf_counter()
            args = {
                "vm": vm,
                "name": name,
                "host_path": host_path,
                "automount": automount,
                "readonly": readonly,
            }
            return _mutate(
                settings,
                "vbox_shared_folder_add",
                args,
                start,
                True,
                "shared_folder_add",
                vm,
                [],
                lambda: storage.shared_folder_add(
                    settings,
                    vm,
                    name,
                    host_path,
                    automount=automount,
                    readonly=readonly,
                ),
            )

        @server.tool()
        def vbox_shared_folder_remove(vm: str, name: str) -> dict:
            """Elimina una carpeta compartida de la VM.

            Args:
                vm: Nombre o UUID de la VM.
                name: Nombre de la carpeta compartida a eliminar.
            """
            start = time.perf_counter()
            args = {"vm": vm, "name": name}
            return _mutate(
                settings,
                "vbox_shared_folder_remove",
                args,
                start,
                True,
                "shared_folder_remove",
                vm,
                [],
                lambda: storage.shared_folder_remove(settings, vm, name),
            )

        @server.tool()
        def vbox_nat_port_forward_add(
            vm: str,
            rule_name: str,
            protocol: str,
            host_port: int,
            guest_port: int,
            guest_ip: str = "",
            host_ip: str = "",
        ) -> dict:
            """Añade una regla de reenvío de puertos NAT (tcp/udp).

            Args:
                vm: Nombre o UUID de la VM.
                rule_name: Nombre identificativo de la regla (sin comas).
                protocol: 'tcp' o 'udp'.
                host_port: Puerto en el host (1-65535).
                guest_port: Puerto en el guest (1-65535).
                guest_ip: IP del guest (vacío = cualquier IP del guest).
                host_ip: IP de escucha en el host (vacío = todas; '127.0.0.1' para solo localhost).
            """
            start = time.perf_counter()
            args = {
                "vm": vm,
                "rule_name": rule_name,
                "protocol": protocol,
                "host_port": host_port,
                "guest_port": guest_port,
                "guest_ip": guest_ip,
                "host_ip": host_ip,
            }
            return _mutate(
                settings,
                "vbox_nat_port_forward_add",
                args,
                start,
                True,
                "nat_port_forward_add",
                vm,
                [],
                lambda: storage.nat_port_forward_add(
                    settings,
                    vm,
                    rule_name,
                    protocol,
                    host_port,
                    guest_port,
                    guest_ip=guest_ip,
                    host_ip=host_ip,
                ),
            )

        @server.tool()
        def vbox_nat_port_forward_remove(vm: str, rule_name: str) -> dict:
            """Elimina una regla de reenvío de puertos NAT por nombre.

            Args:
                vm: Nombre o UUID de la VM.
                rule_name: Nombre exacto de la regla a eliminar.
            """
            start = time.perf_counter()
            args = {"vm": vm, "rule_name": rule_name}
            return _mutate(
                settings,
                "vbox_nat_port_forward_remove",
                args,
                start,
                True,
                "nat_port_forward_remove",
                vm,
                [],
                lambda: storage.nat_port_forward_remove(settings, vm, rule_name),
            )

        @server.tool()
        def vbox_vrde_configure(
            vm: str,
            enabled: bool = True,
            port: int = 3389,
            address: str = "",
            auth_type: str = "null",
            multi_connection: bool = False,
        ) -> dict:
            """Configura el acceso remoto VRDE/RDP de una VM.

            Args:
                vm: Nombre o UUID de la VM.
                enabled: Si es true, habilita VRDE; false lo deshabilita.
                port: Puerto RDP (por defecto 3389).
                address: IP de escucha (vacío = todas las interfaces).
                auth_type: 'null' (sin auth), 'external' o 'guest'.
                multi_connection: Si es true, permite múltiples clientes simultáneos.
            """
            start = time.perf_counter()
            args = {
                "vm": vm,
                "enabled": enabled,
                "port": port,
                "address": address,
                "auth_type": auth_type,
                "multi_connection": multi_connection,
            }
            return _mutate(
                settings,
                "vbox_vrde_configure",
                args,
                start,
                True,
                "vrde_configure",
                vm,
                [],
                lambda: storage.vrde_configure(
                    settings, vm,
                    enabled=enabled, port=port, address=address,
                    auth_type=auth_type, multi_connection=multi_connection,
                ),
            )

        # --------------------- Discos ----------------------

        @server.tool()
        def vbox_disk_create(
            path: str,
            size_mb: int,
            fmt: str = "VDI",
            variant: str = "Standard",
        ) -> dict:
            """Crea un nuevo disco virtual independiente.

            Args:
                path: Ruta donde crear el disco (se añade extensión si falta).
                size_mb: Tamaño del disco en MiB.
                fmt: Formato: 'VDI' (nativo VirtualBox), 'VMDK' (VMware), 'VHD' (Hyper-V).
                variant: 'Standard' (dinámico), 'Fixed' (preasignado), 'Split2G' (dividido).
            """
            start = time.perf_counter()
            args = {"path": path, "size_mb": size_mb, "fmt": fmt, "variant": variant}
            return _mutate(
                settings,
                "vbox_disk_create",
                args,
                start,
                True,
                "disk_create",
                path,
                [],
                lambda: disks.disk_create(settings, path, size_mb, fmt=fmt, variant=variant),
            )

        @server.tool()
        def vbox_disk_attach(
            vm: str,
            disk_path: str,
            controller: str = "sata",
            port: int = 0,
            device: int = 0,
            disk_type: str = "hdd",
        ) -> dict:
            """Adjunta un disco existente a una VM.

            Args:
                vm: Nombre o UUID de la VM.
                disk_path: Ruta al archivo de disco.
                controller: Nombre del controlador ('sata', 'ide', 'scsi', 'nvme').
                port: Puerto del controlador.
                device: Número de dispositivo en el puerto.
                disk_type: 'hdd', 'dvddrive' o 'floppy'.
            """
            start = time.perf_counter()
            args = {
                "vm": vm, "disk_path": disk_path, "controller": controller,
                "port": port, "device": device, "disk_type": disk_type,
            }
            return _mutate(
                settings,
                "vbox_disk_attach",
                args,
                start,
                True,
                "disk_attach",
                vm,
                [],
                lambda: disks.disk_attach(
                    settings, vm, disk_path,
                    controller=controller, port=port, device=device, disk_type=disk_type,
                ),
            )

        @server.tool()
        def vbox_disk_detach(
            vm: str,
            controller: str = "sata",
            port: int = 0,
            device: int = 0,
            confirm: bool = False,
        ) -> dict:
            """Desadjunta un disco de una VM (no lo borra del host). Requiere confirm=true.

            Args:
                vm: Nombre o UUID de la VM.
                controller: Nombre del controlador.
                port: Puerto del controlador.
                device: Número de dispositivo.
                confirm: Debe ser true para ejecutar.
            """
            start = time.perf_counter()
            args = {
                "vm": vm, "controller": controller,
                "port": port, "device": device, "confirm": confirm,
            }
            return _mutate(
                settings,
                "vbox_disk_detach",
                args,
                start,
                confirm,
                "disk_detach",
                vm,
                ["el disco se desadjunta de la VM pero no se borra del host"],
                lambda: disks.disk_detach(settings, vm, controller=controller, port=port, device=device),
            )

        @server.tool()
        def vbox_disk_resize(
            disk_path: str,
            new_size_mb: int,
            confirm: bool = False,
        ) -> dict:
            """Redimensiona un disco VDI (solo se puede ampliar). Requiere confirm=true.

            Args:
                disk_path: Ruta al archivo de disco VDI.
                new_size_mb: Nuevo tamaño en MiB (debe ser mayor que el actual).
                confirm: Debe ser true para ejecutar.
            """
            start = time.perf_counter()
            args = {"disk_path": disk_path, "new_size_mb": new_size_mb, "confirm": confirm}
            return _mutate(
                settings,
                "vbox_disk_resize",
                args,
                start,
                confirm,
                "disk_resize",
                disk_path,
                ["el disco se amplía de forma irreversible"],
                lambda: disks.disk_resize(settings, disk_path, new_size_mb),
            )

        # ---------------------------- Snapshots ----------------------------

        @server.tool()
        def vbox_snapshot_take(
            vm: str,
            name: str,
            description: str = "",
            timeout_seconds: int = 600,
        ) -> dict:
            """Crea un snapshot de la VM (funciona con la VM encendida o apagada).

            Args:
                vm: Nombre o UUID de la VM.
                name: Nombre del snapshot.
                description: Descripción opcional.
                timeout_seconds: Tiempo máximo de espera (1-3600 s).
            """
            start = time.perf_counter()
            args = {
                "vm": vm,
                "name": name,
                "description": description,
                "timeout_seconds": _clamp_timeout(timeout_seconds),
            }
            return _mutate(
                settings,
                "vbox_snapshot_take",
                args,
                start,
                True,
                "snapshot_take",
                vm,
                [],
                lambda: snapshots.snapshot_take(
                    settings,
                    vm,
                    name,
                    description,
                    timeout=_clamp_timeout(timeout_seconds),
                ),
            )

        @server.tool()
        def vbox_snapshot_restore(
            vm: str,
            name: str,
            confirm: bool = False,
            timeout_seconds: int = 600,
        ) -> dict:
            """Restaura un snapshot; descarta el estado actual de la VM. Requiere confirm=true.

            Args:
                vm: Nombre o UUID de la VM.
                name: Nombre del snapshot a restaurar.
                confirm: Debe ser true para ejecutar.
                timeout_seconds: Tiempo máximo de espera (1-3600 s).
            """
            start = time.perf_counter()
            args = {
                "vm": vm,
                "name": name,
                "confirm": confirm,
                "timeout_seconds": _clamp_timeout(timeout_seconds),
            }
            return _mutate(
                settings,
                "vbox_snapshot_restore",
                args,
                start,
                confirm,
                "snapshot_restore",
                vm,
                [f"se descarta el estado actual y se vuelve al snapshot '{name}'"],
                lambda: snapshots.snapshot_restore(
                    settings, vm, name, timeout=_clamp_timeout(timeout_seconds)
                ),
            )

        @server.tool()
        def vbox_snapshot_delete(
            vm: str,
            name: str,
            confirm: bool = False,
            timeout_seconds: int = 600,
        ) -> dict:
            """Borra un snapshot de la VM de forma permanente. Requiere confirm=true.

            Args:
                vm: Nombre o UUID de la VM.
                name: Nombre del snapshot a borrar.
                confirm: Debe ser true para ejecutar.
                timeout_seconds: Tiempo máximo de espera (1-3600 s).
            """
            start = time.perf_counter()
            args = {
                "vm": vm,
                "name": name,
                "confirm": confirm,
                "timeout_seconds": _clamp_timeout(timeout_seconds),
            }
            return _mutate(
                settings,
                "vbox_snapshot_delete",
                args,
                start,
                confirm,
                "snapshot_delete",
                vm,
                [f"se borra el snapshot '{name}' de forma permanente"],
                lambda: snapshots.snapshot_delete(
                    settings, vm, name, timeout=_clamp_timeout(timeout_seconds)
                ),
            )

        @server.tool()
        def vbox_snapshot_rename(
            vm: str,
            old_name: str,
            new_name: str,
            description: str = "",
        ) -> dict:
            """Renombra un snapshot existente (opcionalmente cambia su descripción).

            Args:
                vm: Nombre o UUID de la VM.
                old_name: Nombre actual del snapshot.
                new_name: Nuevo nombre del snapshot.
                description: Nueva descripción (opcional; si está vacía no se modifica).
            """
            start = time.perf_counter()
            args = {"vm": vm, "old_name": old_name, "new_name": new_name, "description": description}
            return _mutate(
                settings,
                "vbox_snapshot_rename",
                args,
                start,
                True,
                "snapshot_rename",
                vm,
                [],
                lambda: lifecycle.snapshot_rename(settings, vm, old_name, new_name, description),
            )

        # ------------------------- Export/Import -------------------------

        @server.tool()
        def vbox_export_vm(
            vm: str,
            output: str,
            fmt: str = "ova",
            manifest: bool = True,
            description: str = "",
            timeout_seconds: int = 600,
        ) -> dict:
            """Exporta una VM a un archivo OVA u OVF.

            Args:
                vm: Nombre o UUID de la VM (debe estar apagada).
                output: Ruta de salida del archivo OVA/OVF.
                fmt: Formato: 'ova' (un solo archivo), 'ovf09', 'ovf10' o 'ovf20'.
                manifest: Si es true, genera un archivo de manifiesto SHA.
                description: Descripción de la VM en el OVF.
                timeout_seconds: Tiempo máximo de espera (1-3600 s).
            """
            start = time.perf_counter()
            args = {
                "vm": vm, "output": output, "fmt": fmt,
                "manifest": manifest, "description": description,
            }
            return _mutate(
                settings,
                "vbox_export_vm",
                args,
                start,
                True,
                "export_vm",
                vm,
                [],
                lambda: export.export_vm(
                    settings, vm, output, fmt=fmt,
                    manifest=manifest, description=description,
                    timeout=_clamp_timeout(timeout_seconds),
                ),
            )

        @server.tool()
        def vbox_import_vm(
            path: str,
            name: str = "",
            base_folder: str = "",
            cpus: int | None = None,
            memory_mb: int | None = None,
            timeout_seconds: int = 600,
        ) -> dict:
            """Importa una VM desde un archivo OVA u OVF.

            Args:
                path: Ruta al archivo OVA/OVF.
                name: Nombre de la VM importada (vacío = usa el nombre del OVF).
                base_folder: Carpeta donde almacenar la VM (vacío = carpeta por defecto).
                cpus: Sobreescribe el número de vCPUs del OVF.
                memory_mb: Sobreescribe la RAM del OVF (MiB).
                timeout_seconds: Tiempo máximo de espera (1-3600 s).
            """
            start = time.perf_counter()
            args = {
                "path": path, "name": name, "base_folder": base_folder,
                "cpus": cpus, "memory_mb": memory_mb,
            }
            return _mutate(
                settings,
                "vbox_import_vm",
                args,
                start,
                True,
                "import_vm",
                path,
                [],
                lambda: export.import_vm(
                    settings, path, name=name, base_folder=base_folder,
                    cpus=cpus, memory_mb=memory_mb,
                    timeout=_clamp_timeout(timeout_seconds),
                ),
            )

        # ------------------------- Guest control -------------------------

        @server.tool()
        def vbox_guest_exec(
            vm: str,
            user: str,
            password: str,
            exe: str,
            args: list[str] | None = None,
            timeout: int = 60,
            env: dict[str, str] | None = None,
            working_dir: str = "",
            stdin: str | None = None,
        ) -> dict:
            """Ejecuta un comando dentro del guest con Guest Additions y devuelve stdout/stderr.

            Args:
                vm: Nombre o UUID de la VM.
                user: Usuario del guest.
                password: Contraseña del usuario del guest.
                exe: Ruta completa al ejecutable dentro del guest.
                args: Argumentos del ejecutable.
                timeout: Segundos de timeout para la ejecución (1-3600).
                env: Variables de entorno adicionales para el proceso guest.
                working_dir: Directorio de trabajo dentro del guest.
                stdin: Texto a enviar al stdin del proceso guest (opcional).
            """
            start = time.perf_counter()
            timeout = _clamp_timeout(timeout)
            audit_args = {
                "vm": vm,
                "user": user,
                "password": password,
                "exe": exe,
                "args": args or [],
                "timeout": timeout,
                "env": env or {},
                "working_dir": working_dir,
                "stdin": stdin,
            }
            return _mutate(
                settings,
                "vbox_guest_exec",
                audit_args,
                start,
                True,
                "guest_exec",
                vm,
                [],
                lambda: guest.guest_exec(
                    settings,
                    vm,
                    user,
                    password,
                    exe,
                    args=args,
                    timeout=timeout,
                    env=env,
                    working_dir=working_dir or None,
                    stdin=stdin,
                ),
            )

        @server.tool()
        def vbox_guest_run_script(
            vm: str,
            user: str,
            password: str,
            script_content: str,
            interpreter: str = "/bin/sh",
            timeout: int = 60,
            env: dict[str, str] | None = None,
            working_dir: str = "",
        ) -> dict:
            """Envía y ejecuta un script de texto en el guest. Más cómodo que guest_exec para scripts.

            El script se escribe en un temporal del host, se copia al guest, se ejecuta y se limpia.

            Args:
                vm: Nombre o UUID de la VM.
                user: Usuario del guest.
                password: Contraseña del usuario del guest.
                script_content: Contenido completo del script (texto).
                interpreter: Intérprete a usar (por defecto '/bin/sh'; usa '/bin/bash', 'python3', etc.).
                timeout: Segundos de timeout (1-3600).
                env: Variables de entorno adicionales.
                working_dir: Directorio de trabajo dentro del guest.
            """
            start = time.perf_counter()
            timeout = _clamp_timeout(timeout)
            audit_args = {
                "vm": vm,
                "user": user,
                "password": password,
                "interpreter": interpreter,
                "script_length": len(script_content),
                "timeout": timeout,
            }
            return _mutate(
                settings,
                "vbox_guest_run_script",
                audit_args,
                start,
                True,
                "guest_run_script",
                vm,
                [],
                lambda: guest.guest_run_script(
                    settings,
                    vm,
                    user,
                    password,
                    script_content,
                    interpreter=interpreter,
                    timeout=timeout,
                    env=env,
                    working_dir=working_dir or None,
                ),
            )

        @server.tool()
        def vbox_guest_copy_to(
            vm: str,
            user: str,
            password: str,
            host_path: str,
            guest_path: str,
            recursive: bool = False,
            timeout_seconds: int = 600,
        ) -> dict:
            """Copia un archivo o carpeta del host al guest (requiere Guest Additions).

            Args:
                vm: Nombre o UUID de la VM.
                user: Usuario del guest.
                password: Contraseña del usuario del guest.
                host_path: Ruta del archivo/carpeta en el host.
                guest_path: Ruta de destino en el guest.
                recursive: Si es true, copia carpetas de forma recursiva.
                timeout_seconds: Tiempo máximo de espera (1-3600 s).
            """
            start = time.perf_counter()
            audit_args = {
                "vm": vm,
                "user": user,
                "password": password,
                "host_path": host_path,
                "guest_path": guest_path,
                "recursive": recursive,
                "timeout_seconds": _clamp_timeout(timeout_seconds),
            }
            return _mutate(
                settings,
                "vbox_guest_copy_to",
                audit_args,
                start,
                True,
                "guest_copy_to",
                vm,
                [],
                lambda: guest.guest_copy_to(
                    settings,
                    vm,
                    user,
                    password,
                    host_path,
                    guest_path,
                    recursive=recursive,
                    timeout=_clamp_timeout(timeout_seconds),
                ),
            )

        @server.tool()
        def vbox_guest_copy_from(
            vm: str,
            user: str,
            password: str,
            guest_path: str,
            host_path: str,
            recursive: bool = False,
            timeout_seconds: int = 600,
        ) -> dict:
            """Copia un archivo o carpeta del guest al host (requiere Guest Additions).

            Args:
                vm: Nombre o UUID de la VM.
                user: Usuario del guest.
                password: Contraseña del usuario del guest.
                guest_path: Ruta del archivo/carpeta en el guest.
                host_path: Ruta de destino en el host.
                recursive: Si es true, copia carpetas de forma recursiva.
                timeout_seconds: Tiempo máximo de espera (1-3600 s).
            """
            start = time.perf_counter()
            audit_args = {
                "vm": vm,
                "user": user,
                "password": password,
                "guest_path": guest_path,
                "host_path": host_path,
                "recursive": recursive,
                "timeout_seconds": _clamp_timeout(timeout_seconds),
            }
            return _mutate(
                settings,
                "vbox_guest_copy_from",
                audit_args,
                start,
                True,
                "guest_copy_from",
                vm,
                [],
                lambda: guest.guest_copy_from(
                    settings,
                    vm,
                    user,
                    password,
                    guest_path,
                    host_path,
                    recursive=recursive,
                    timeout=_clamp_timeout(timeout_seconds),
                ),
            )

        # ------------------------------ GUI ------------------------------

        @server.tool()
        def vbox_send_keys(
            vm: str,
            text: str,
            delay_ms: int = 50,
            method: str = "string",
        ) -> dict:
            """Envía teclado a la VM activa.

            Tokens especiales: <enter>, <tab>, <esc>, <space>, <backspace>,
            <up>, <down>, <left>, <right>, <home>, <end>, <pageup>, <pagedown>,
            <f1>-<f12>, <insert>, <delete>.

            Args:
                vm: Nombre o UUID de la VM.
                text: Texto o secuencia de teclas con tokens entre <>.
                delay_ms: Pausa entre chunks de scancodes en ms.
                method: 'string' (rápido, solo ASCII sin tokens) o
                        'scancode' (lento, soporta tokens especiales).
            """
            start = time.perf_counter()
            args = {"vm": vm, "text": text, "delay_ms": delay_ms, "method": method}
            return _mutate(
                settings,
                "vbox_send_keys",
                args,
                start,
                True,
                "send_keys",
                vm,
                [],
                lambda: gui.send_keys(settings, vm, text, delay_ms=delay_ms, method=method),
            )

        @server.tool()
        def vbox_mouse_move(vm: str, x: int, y: int) -> dict:
            """Mueve el ratón a coordenadas del framebuffer del guest.

            Solo funciona en Windows con la VM en modo GUI y la ventana en primer plano.

            Args:
                vm: Nombre o UUID de la VM.
                x: Coordenada X en píxeles del framebuffer del guest.
                y: Coordenada Y en píxeles del framebuffer del guest.
            """
            start = time.perf_counter()
            args = {"vm": vm, "x": x, "y": y}
            return _mutate(
                settings,
                "vbox_mouse_move",
                args,
                start,
                True,
                "mouse_move",
                vm,
                [],
                lambda: gui.mouse_move(settings, vm, x, y),
            )

        @server.tool()
        def vbox_mouse_click(
            vm: str,
            x: int,
            y: int,
            button: str = "left",
            double: bool = False,
        ) -> dict:
            """Hace clic en coordenadas del framebuffer del guest.

            Solo funciona en Windows con la VM en modo GUI y la ventana en primer plano.

            Args:
                vm: Nombre o UUID de la VM.
                x: Coordenada X en píxeles del framebuffer del guest.
                y: Coordenada Y en píxeles del framebuffer del guest.
                button: 'left', 'right' o 'middle'.
                double: Si es true, realiza doble clic.
            """
            start = time.perf_counter()
            args = {"vm": vm, "x": x, "y": y, "button": button, "double": double}
            return _mutate(
                settings,
                "vbox_mouse_click",
                args,
                start,
                True,
                "mouse_click",
                vm,
                [],
                lambda: gui.mouse_click(settings, vm, x, y, button=button, double=double),
            )

    # ----------------------------- Resources -----------------------------

    @server.resource("vbox://health", name="health", title="Health Check")
    async def _health() -> dict:
        """Health check del servidor MCP y VirtualBox."""
        return await health_check(settings)

    @server.resource("vbox://version", name="version", title="Version Info")
    async def _version() -> dict:
        """Información de versión del servidor y VBoxManage."""
        return await version_info(settings)

    @server.resource("vbox://host", name="host", title="Host Info")
    async def _host() -> dict:
        """Información del host desde VBoxManage."""
        return await host_info_resource(settings)

    return server
