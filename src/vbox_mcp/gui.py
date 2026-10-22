"""Captura de pantalla, teclado y ratón para VMs de VirtualBox."""

from __future__ import annotations

import os
import re
import struct
import sys
import tempfile
import time
from pathlib import Path

from .config import Settings
from .vboxmanage import VBoxError, run, vm_info

_BASE_SCANCODES = {
    "a": "1e", "b": "30", "c": "2e", "d": "20", "e": "12", "f": "21", "g": "22",
    "h": "23", "i": "17", "j": "24", "k": "25", "l": "26", "m": "32", "n": "31",
    "o": "18", "p": "19", "q": "10", "r": "13", "s": "1f", "t": "14", "u": "16",
    "v": "2f", "w": "11", "x": "2d", "y": "15", "z": "2c",
    "1": "02", "2": "03", "3": "04", "4": "05", "5": "06", "6": "07", "7": "08",
    "8": "09", "9": "0a", "0": "0b",
    "-": "0c", "=": "0d", "[": "1a", "]": "1b", "\\": "2b", ";": "27", "'": "28",
    "`": "29", ",": "33", ".": "34", "/": "35", " ": "39",
}

_SHIFTED_SCANCODES = {
    "!": "1", "@": "2", "#": "3", "$": "4", "%": "5", "^": "6", "&": "7", "*": "8",
    "(": "9", ")": "0", "_": "-", "+": "=", "{": "[", "}": "]", "|": "\\", ":": ";",
    '"': "'", "<": ",", ">": ".", "?": "/", "~": "`",
}

_SPECIAL_SCANCODES = {
    "enter": ["1c", "9c"],
    "esc": ["01", "81"],
    "escape": ["01", "81"],
    "tab": ["0f", "8f"],
    "space": ["39", "b9"],
    "backspace": ["0e", "8e"],
    "delete": ["53", "d3"],
    "insert": ["52", "d2"],
    "up": ["48", "c8"],
    "down": ["50", "d0"],
    "left": ["4b", "cb"],
    "right": ["4d", "cd"],
    "home": ["47", "c7"],
    "end": ["4f", "cf"],
    "pageup": ["49", "c9"],
    "pagedown": ["51", "d1"],
    "f1": ["3b", "bb"],
    "f2": ["3c", "bc"],
    "f3": ["3d", "bd"],
    "f4": ["3e", "be"],
    "f5": ["3f", "bf"],
    "f6": ["40", "c0"],
    "f7": ["41", "c1"],
    "f8": ["42", "c2"],
    "f9": ["43", "c3"],
    "f10": ["44", "c4"],
    "f11": ["57", "d7"],
    "f12": ["58", "d8"],
}

_SHIFT_MAKE = "2a"
_SHIFT_BREAK = "aa"
_TOKEN_RE = re.compile(r"<([A-Za-z0-9]+)>|(.)", re.S)

_BUTTONS = {
    "left": (0x0002, 0x0004),
    "right": (0x0008, 0x0010),
    "middle": (0x0020, 0x0040),
}


def _release(make: str) -> str:
    return format(int(make, 16) | 0x80, "02x")


def _char_codes(char: str) -> list[str]:
    if char in ("\n", "\r"):
        return list(_SPECIAL_SCANCODES["enter"])
    if char == "\t":
        return list(_SPECIAL_SCANCODES["tab"])
    if "a" <= char <= "z" or char in _BASE_SCANCODES:
        make = _BASE_SCANCODES[char]
        return [make, _release(make)]
    if "A" <= char <= "Z":
        make = _BASE_SCANCODES[char.lower()]
        return [_SHIFT_MAKE, make, _release(make), _SHIFT_BREAK]
    if char in _SHIFTED_SCANCODES:
        make = _BASE_SCANCODES[_SHIFTED_SCANCODES[char]]
        return [_SHIFT_MAKE, make, _release(make), _SHIFT_BREAK]
    raise VBoxError(
        f"Carácter no soportado por scancodes US: {char!r}. "
        "Los scancodes solo cubren ASCII; usa method='string' para texto simple."
    )


def scancodes_for(text: str) -> list[str]:
    codes: list[str] = []
    for match in _TOKEN_RE.finditer(text):
        token, char = match.group(1), match.group(2)
        if token is not None:
            special = _SPECIAL_SCANCODES.get(token.lower())
            if special is None:
                raise VBoxError(f"Token de tecla desconocido: <{token}>")
            codes.extend(special)
        elif char:
            codes.extend(_char_codes(char))
    return codes


def screenshot(settings: Settings, vm: str, display: int = 0) -> Path:
    directory = Path(tempfile.gettempdir()) / "vbox-mcp-shots"
    directory.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "_", vm) or "vm"
    fd, name = tempfile.mkstemp(
        prefix=f"{safe}-", suffix=f"-{display}.png", dir=str(directory)
    )
    os.close(fd)
    path = Path(name)

    try:
        run(
            ["controlvm", vm, "screenshotpng", str(path), str(display)],
            settings=settings,
        )
        if path.stat().st_size == 0:
            raise VBoxError(
                "VBoxManage no generó el screenshot. Comprueba que la VM esté encendida "
                "y no en estado guardado."
            )
    except Exception:
        path.unlink(missing_ok=True)
        raise
    return path


def send_keys(
    settings: Settings,
    vm: str,
    text: str,
    delay_ms: int = 50,
    method: str = "string",
) -> dict[str, object]:
    if method not in {"string", "scancode"}:
        raise VBoxError("method debe ser 'string' o 'scancode'")

    has_tokens = bool(re.search(r"<[A-Za-z0-9]+>", text))
    if method == "string" and not has_tokens:
        run(["controlvm", vm, "keyboardputstring", text], settings=settings)
        return {"vm": vm, "method": "string", "chars": len(text)}

    codes = scancodes_for(text)
    for index in range(0, len(codes), 64):
        chunk = codes[index:index + 64]
        run(["controlvm", vm, "keyboardputscancode", *chunk], settings=settings)
        if delay_ms > 0 and index + 64 < len(codes):
            time.sleep(delay_ms / 1000)

    return {"vm": vm, "method": "scancode", "codes": codes}


def png_size(path: str | Path) -> tuple[int, int]:
    with open(path, "rb") as fh:
        header = fh.read(24)
    if len(header) < 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
        raise VBoxError(f"El archivo no es un PNG válido: {path}")
    width, height = struct.unpack(">II", header[16:24])
    return int(width), int(height)


def map_coords(
    x: int,
    y: int,
    guest_w: int,
    guest_h: int,
    client_w: int,
    client_h: int,
) -> tuple[int, int]:
    if guest_w <= 0 or guest_h <= 0 or client_w <= 0 or client_h <= 0:
        raise VBoxError("dimensiones inválidas para mapear coordenadas")

    scale = min(client_w / guest_w, client_h / guest_h)
    drawn_w = guest_w * scale
    drawn_h = guest_h * scale
    offset_x = (client_w - drawn_w) / 2
    offset_y = (client_h - drawn_h) / 2

    px = int(round(offset_x + x * scale))
    py = int(round(offset_y + y * scale))
    px = max(0, min(client_w - 1, px))
    py = max(0, min(client_h - 1, py))
    return px, py


def _require_win32() -> None:
    if sys.platform != "win32":
        raise VBoxError("El control de ratón solo está soportado en Windows.")


def _require_mouse(settings: Settings) -> None:
    _require_win32()
    if not settings.allow_mouse:
        raise VBoxError("El control de ratón está deshabilitado (VBOX_MCP_ALLOW_MOUSE=false).")


def _window_title(vm: str) -> str:
    return f"{vm} [Running] - Oracle VirtualBox"


def _resolve_window_name(settings: Settings, vm: str) -> str:
    try:
        info = vm_info(settings, vm)
    except (VBoxError, OSError):
        return vm
    name = info.get("summary", {}).get("name")
    return str(name) if name else vm


def _find_window(vm: str) -> int:
    import ctypes

    hwnd = ctypes.windll.user32.FindWindowW(None, _window_title(vm))
    if not hwnd:
        raise VBoxError(
            f"No se encontró la ventana '{_window_title(vm)}'. "
            "Arranca la VM con mode='gui' para poder usar el ratón."
        )
    return int(hwnd)


def _largest_child(rects: list[tuple[int, int, int, int, int]]) -> int | None:
    best: int | None = None
    best_area = 0
    for hwnd, left, top, right, bottom in rects:
        area = max(0, right - left) * max(0, bottom - top)
        if area > best_area:
            best = hwnd
            best_area = area
    return best


def _child_rects(hwnd: int) -> list[tuple[int, int, int, int, int]]:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    rects: list[tuple[int, int, int, int, int]] = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def collect(child: int, _lparam: int) -> bool:
        if not user32.IsWindowVisible(child):
            return True
        rect = wintypes.RECT()
        if not user32.GetClientRect(child, ctypes.byref(rect)):
            return True
        width = int(rect.right - rect.left)
        height = int(rect.bottom - rect.top)
        if width > 0 and height > 0:
            rects.append((int(child), 0, 0, width, height))
        return True

    user32.EnumChildWindows(hwnd, collect, 0)
    return rects


def _display_window(vm: str) -> tuple[int, int, int]:
    """Devuelve la ventana del framebuffer del guest y su tamaño de cliente.

    La ventana de nivel superior incluye barra de menú, toolbar y barra de estado;
    el framebuffer es el hijo visible de mayor área.
    """
    import ctypes
    from ctypes import wintypes

    top = _find_window(vm)
    display = _largest_child(_child_rects(top)) or top
    rect = wintypes.RECT()
    if not ctypes.windll.user32.GetClientRect(display, ctypes.byref(rect)):
        raise VBoxError("No se pudo obtener el tamaño de la ventana de la VM.")
    return display, int(rect.right - rect.left), int(rect.bottom - rect.top)


def _client_size(vm: str) -> tuple[int, int]:
    _display, width, height = _display_window(vm)
    return width, height


def _foreground_ok(hwnd: int, user32: object) -> bool:
    return bool(
        user32.GetForegroundWindow() == hwnd
        and user32.IsWindowVisible(hwnd)
        and not user32.IsIconic(hwnd)
    )


def _focus_and_move(
    vm: str, px: int, py: int, display_hwnd: int | None = None
) -> None:
    import ctypes
    from ctypes import wintypes

    user32 = ctypes.windll.user32
    top = _find_window(vm)
    if display_hwnd is None:
        display_hwnd = _display_window(vm)[0]

    for _ in range(3):
        user32.SetForegroundWindow(top)
        time.sleep(0.05)
        if _foreground_ok(top, user32):
            break
    else:
        raise VBoxError(
            "No se pudo poner la ventana de la VM en primer plano. "
            "Haz clic en ella y vuelve a intentarlo."
        )

    point = wintypes.POINT(px, py)
    if not user32.ClientToScreen(display_hwnd, ctypes.byref(point)):
        raise VBoxError("No se pudo mapear la coordenada al framebuffer de la VM.")
    if not user32.SetCursorPos(int(point.x), int(point.y)):
        raise VBoxError("No se pudo mover el cursor del sistema.")


def _move_to(vm: str, px: int, py: int) -> None:
    _focus_and_move(vm, px, py)


def _click_at(vm: str, px: int, py: int, button: str, double: bool) -> None:
    import ctypes

    if button not in _BUTTONS:
        raise VBoxError(f"button debe ser uno de {sorted(_BUTTONS)}")
    down, up = _BUTTONS[button]
    user32 = ctypes.windll.user32
    display_hwnd = _display_window(vm)[0]
    _focus_and_move(vm, px, py, display_hwnd)
    if not _foreground_ok(_find_window(vm), user32):
        raise VBoxError(
            "La ventana de la VM perdió el foco antes de hacer clic; no se envió el clic."
        )
    time.sleep(0.05)
    for _ in range(2 if double else 1):
        user32.mouse_event(down, 0, 0, 0, 0)
        user32.mouse_event(up, 0, 0, 0, 0)
        time.sleep(0.05)


def _guest_size(settings: Settings, vm: str) -> tuple[int, int]:
    shot = screenshot(settings, vm)
    try:
        return png_size(shot)
    finally:
        shot.unlink(missing_ok=True)


def mouse_move(settings: Settings, vm: str, x: int, y: int) -> dict[str, object]:
    _require_mouse(settings)
    window = _resolve_window_name(settings, vm)
    guest_w, guest_h = _guest_size(settings, vm)
    client_w, client_h = _client_size(window)
    px, py = map_coords(x, y, guest_w, guest_h, client_w, client_h)
    _move_to(window, px, py)
    return {"vm": vm, "action": "mouse_move", "x": px, "y": py}


def mouse_click(
    settings: Settings,
    vm: str,
    x: int,
    y: int,
    button: str = "left",
    double: bool = False,
) -> dict[str, object]:
    _require_mouse(settings)
    window = _resolve_window_name(settings, vm)
    guest_w, guest_h = _guest_size(settings, vm)
    client_w, client_h = _client_size(window)
    px, py = map_coords(x, y, guest_w, guest_h, client_w, client_h)
    _click_at(window, px, py, button, double)
    return {"vm": vm, "action": "mouse_click", "x": px, "y": py, "button": button, "double": double}
