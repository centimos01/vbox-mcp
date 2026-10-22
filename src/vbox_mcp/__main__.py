"""Arranque del servidor MCP por stdio."""

from __future__ import annotations

from .config import Settings
from .server import build_server


def main() -> None:
    build_server(Settings.from_env()).run("stdio")


if __name__ == "__main__":
    main()
