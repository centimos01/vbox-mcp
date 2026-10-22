"""Definición de las tools MCP."""

from __future__ import annotations

import time
from typing import Any, Callable

from mcp.server.mcpserver import Image, MCPServer
from mcp.server.mcpserver.exceptions import ToolError

from . import guest, gui, lifecycle, snapshots, storage
from .config import Settings
from .safety import ConfirmationRequired, audit, ensure_writable, require_confirm
from .vboxmanage import (
    VBoxError,
    guest_ip,
    list_networks,
    list_ostypes,
    list_vms,
    snapshot_list,
    vm_info,
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
        version="0.1.0",
        instructions=(
            "Controla VirtualBox local mediante VBoxManage. Identifica las VMs por "
            "nombre o UUID. Las operaciones destructivas requieren confirm=true."
        ),
    )

    # ----------------------------- Lectura -----------------------------

    @server.tool()
    def vbox_list_vms(running_only: bool = False) -> dict:
        """Lista las máquinas virtuales registradas y su estado."""
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
    def vbox_vm_info(vm: str) -> dict:
        """Muestra configuración y estado de una VM (CPU, RAM, discos, red)."""
        start = time.perf_counter()
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
        """Lista los snapshots de una VM."""
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
    def vbox_guest_ip(vm: str) -> dict:
        """Obtiene la IPv4 que reporta Guest Additions para una VM encendida."""
        start = time.perf_counter()
        return _read(
            settings,
            "vbox_guest_ip",
            {"vm": vm},
            start,
            lambda: {"vm": vm, "ip": guest_ip(settings, vm)},
        )

    @server.tool()
    def vbox_screenshot(vm: str, display: int = 0) -> Image:
        """Captura la pantalla de una VM encendida y devuelve el PNG."""
        start = time.perf_counter()
        try:
            path = gui.screenshot(settings, vm, display)
            try:
                data = path.read_bytes()
            finally:
                path.unlink(missing_ok=True)
        except (OSError, VBoxError) as exc:
            audit(
                settings,
                "vbox_screenshot",
                {"vm": vm, "display": display},
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

    if not settings.readonly:
        # ------------------------- Ciclo de vida -------------------------

        @server.tool()
        def vbox_start_vm(vm: str, mode: str = "headless") -> dict:
            """Arranca una VM. mode: headless (sin ventana) o gui (necesario para el ratón)."""
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
            """Apaga una VM. mode: acpi (suave), save (guarda estado) o poweroff (cortar; requiere confirm)."""
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
            """Pausa una VM en ejecución."""
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
            """Reanuda una VM pausada."""
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
            """Reinicia una VM a lo bruto (equivale a pulsar Reset; requiere confirm)."""
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
            """Crea y registra una VM. ostype sale de vbox_list_ostypes; disk_mb=0 no crea disco."""
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
            nic: str | None = None,
            adapter: str = "",
        ) -> dict:
            """Modifica CPU, RAM o el modo de la NIC 1 (nat, bridged, hostonly, none)."""
            start = time.perf_counter()
            args = {
                "vm": vm,
                "cpus": cpus,
                "memory_mb": memory_mb,
                "nic": nic,
                "adapter": adapter,
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
                    nic=nic,
                    adapter=adapter or None,
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
            """Clona una VM. mode: full (copia completa) o linked (disco enlazado, rápido)."""
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
            """Desregistra una VM. Solo borra sus discos si delete_disks=true. Requiere confirm."""
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

        # --------------------- Almacenamiento y red ---------------------

        @server.tool()
        def vbox_attach_iso(
            vm: str,
            iso_path: str,
            controller: str = "sata",
            port: int = 1,
        ) -> dict:
            """Conecta un ISO a la unidad óptica de una VM."""
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
            """Desconecta el ISO de la unidad óptica de una VM."""
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
            """Comparte una carpeta del host con la VM (requiere Guest Additions)."""
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
            """Elimina una carpeta compartida de la VM."""
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
            """Añade una regla de reenvío de puertos NAT (tcp/udp)."""
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
            """Elimina una regla de reenvío de puertos NAT por nombre."""
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

        # ---------------------------- Snapshots ----------------------------

        @server.tool()
        def vbox_snapshot_take(
            vm: str,
            name: str,
            description: str = "",
            timeout_seconds: int = 600,
        ) -> dict:
            """Crea un snapshot de la VM."""
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
            """Restaura un snapshot; descarta el estado actual de la VM. Requiere confirm."""
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
            """Borra un snapshot de la VM. Requiere confirm."""
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
        ) -> dict:
            """Ejecuta un comando dentro del guest con Guest Additions y devuelve stdout/stderr."""
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
            """Copia un archivo o carpeta del host al guest."""
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
            """Copia un archivo o carpeta del guest al host."""
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
            """Envía teclado a la VM. Tokens: <enter>, <tab>, <esc>, <f2>, <down>..."""
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
            """Mueve el ratón a coordenadas del framebuffer del guest (solo Windows, VM en modo GUI)."""
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
            """Hace clic en coordenadas del framebuffer del guest (solo Windows, VM en modo GUI)."""
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

    return server
