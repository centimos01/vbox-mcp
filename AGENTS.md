# vbox-mcp — Agent Guide

## Quick Start
```bash
# Install in editable mode
pip install -e .

# Run server (stdio)
python -m vbox_mcp

# Run tests (unit, no VirtualBox required)
pytest

# Run integration tests (requires VirtualBox)
pytest -m integration -v
```

## Project Structure
```
src/vbox_mcp/          # Package (src layout)
├── __main__.py        # Entry point: build_server(Settings.from_env()).run("stdio")
├── server.py          # All 49 MCP tools + 3 resources registered
├── config.py          # Settings from env vars (see below)
├── vboxmanage.py      # VBoxManage wrapper + parsing
├── lifecycle.py       # VM create/start/stop/clone/delete/modify/group
├── storage.py         # ISO, shared folders, NAT port forwarding, VRDE
├── disks.py           # Disk create/attach/detach/resize/info, list_media
├── export.py          # OVA/OVF export/import
├── snapshots.py       # Snapshot take/restore/delete/rename/list
├── guest.py           # guest_exec, guest_run_script, guest_copy_to/from
├── gui.py             # screenshot, send_keys, mouse_move/click
├── metrics.py         # audit log reading + stats
├── resources.py       # MCP resources: vbox://health, vbox://version, vbox://host
├── safety.py          # readonly mode, confirmations, audit logging, redaction
└── parsing.py         # VBoxManage output parsers
```

## Key Commands
| Task | Command |
|------|---------|
| Unit tests | `pytest` (164 tests, ~22s) |
| Integration tests | `pytest -m integration -v` |
| Single test file | `pytest tests/test_disks.py -v` |
| Typecheck | `mypy src/vbox_mcp` (if configured) |
| Build wheel | `pip wheel . -w dist` |

## Environment Variables (all optional)
| Variable | Default | Purpose |
|----------|---------|---------|
| `VBOX_MANAGE_PATH` | auto-detect | Path to VBoxManage executable |
| `VBOX_MCP_READONLY` | `false` | Hide mutating tools when `true` |
| `VBOX_MCP_TIMEOUT_SECONDS` | `60` | Global VBoxManage timeout |
| `VBOX_MCP_AUDIT_LOG` | `%LOCALAPPDATA%\vbox-mcp\audit.log` | JSONL audit log |
| `VBOX_MCP_ALLOW_MOUSE` | `true` | Enable mouse control (Windows only) |
| `VBOX_MCP_GUEST_USER` | — | Default guest username |
| `VBOX_MCP_GUEST_PASSWORD` | — | Default guest password |
| `VBOX_MCP_RETRIES` | `0` | Retry transient errors (0-5) |
| `VBOX_MCP_RATE_LIMIT` | `0` | Calls/minute per tool (0=unlimited) |
| `VBOX_MCP_DANGEROUS_VM_PATTERNS` | — | Comma-separated fnmatch patterns to block VM names |

## Testing Notes
- Uses `tests/fake_vboxmanage.py` — a fake VBoxManage that logs calls and returns configured responses
- Fixtures in `tests/conftest.py`: `fake` (FakeVBox), `settings` (Settings with fake VBoxManage)
- Unit tests mock VBoxManage via the fake; integration tests hit real VirtualBox
- `addopts = "-m 'not integration'"` — unit tests run by default

## Architecture Notes
- **Single entrypoint**: `__main__.py` → `build_server(Settings.from_env()).run("stdio")`
- **Settings** is a frozen dataclass loaded once at startup from env vars
- **VBoxManage calls** go through `run()` / `run_process()` in `vboxmanage.py` — all args as list, no shell
- **Tools** are registered via `@server.tool()` on the MCPServer instance in `build_server()`
- **Resources** via `@server.resource("vbox://...")`
- **Destructive ops** require `confirm=true` or return `{"status": "confirmation_required", ...}`
- **Audit log**: JSONL, secrets redacted (password, secret, token, etc.)
- **Guest passwords**: passed via temp file (`--passwordfile`), never in argv or logs

## Common Gotchas
- Windows-only: `vbox_mouse_*`, `vbox_send_keys` (needs GUI mode, window focused)
- `vbox_guest_*` and shared folders require Guest Additions in VM
- Shared folders added while VM running are transient (lost on shutdown)
- `vbox_clone_vm(mode="linked")` requires a snapshot name
- `vbox_screenshot`/`vbox_send_keys`/`vbox_mouse_*` need VM running (not saved state)
- Per-tool timeouts: use `timeout_seconds` param on long ops (clone, export, import, snapshots, copy)

## Adding a New Tool
1. Implement logic in relevant module (`lifecycle.py`, `storage.py`, etc.)
2. Import and register in `server.py` inside `build_server()`
3. Use `_read()` for read-only, `_mutate()` for mutating (handles confirm/readonly/audit)
4. Add tests in `tests/test_<module>.py` using `fake` fixture