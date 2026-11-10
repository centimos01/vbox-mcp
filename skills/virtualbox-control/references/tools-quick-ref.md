# VBox MCP — Tools Quick Reference

All tools are provided by the `vbox-mcp` MCP server. Identify VMs by name or UUID.

---

## Visual / GUI

| Tool | Key Params | Notes |
|------|-----------|-------|
| `vbox_screenshot` | `vm`, `display=0`, `output_path=""` | Returns PNG image inline, or saves to file if `output_path` given |
| `vbox_send_keys` | `vm`, `text`, `delay_ms=50`, `method="string"` | Use `<enter>`, `<tab>`, etc. Auto-switches to scancode when tokens present |
| `vbox_mouse_click` | `vm`, `x`, `y`, `button="left"`, `double=false` | Guest framebuffer pixel coords. Requires GUI mode + Windows host |
| `vbox_mouse_move` | `vm`, `x`, `y` | Move cursor without clicking. Same requirements as mouse_click |

## Guest Control (Requires Guest Additions)

| Tool | Key Params | Notes |
|------|-----------|-------|
| `vbox_guest_exec` | `vm`, `user`, `password`, `exe`, `args=[]`, `timeout=60`, `env={}`, `working_dir=""`, `stdin=null` | Returns `exit_code`, `stdout`, `stderr` |
| `vbox_guest_run_script` | `vm`, `user`, `password`, `script_content`, `interpreter="/bin/sh"`, `timeout=60` | Copies script to guest, runs it, cleans up |
| `vbox_guest_copy_to` | `vm`, `user`, `password`, `host_path`, `guest_path`, `recursive=false` | Host → Guest file transfer |
| `vbox_guest_copy_from` | `vm`, `user`, `password`, `guest_path`, `host_path`, `recursive=false` | Guest → Host file transfer |

## VM Lifecycle

| Tool | Key Params | Notes |
|------|-----------|-------|
| `vbox_list_vms` | `running_only=false` | Lists all registered VMs with state, group, description |
| `vbox_vm_info` | `vm`, `extended=false` | Detailed config. `extended=true` adds disks, NAT, shared folders |
| `vbox_start_vm` | `vm`, `mode="headless"` | **Use `mode="gui"` for mouse control!** Also `"separate"` |
| `vbox_stop_vm` | `vm`, `mode="acpi"`, `confirm=false` | `"acpi"` (soft), `"save"` (save state), `"poweroff"` (hard, needs confirm) |
| `vbox_pause_vm` | `vm` | Freezes CPU without powering off |
| `vbox_resume_vm` | `vm` | Resumes a paused VM |
| `vbox_reset_vm` | `vm`, `confirm=false` | Hard reset — needs `confirm=true` |
| `vbox_create_vm` | `name`, `ostype`, `cpus=2`, `memory_mb=2048`, `disk_mb=0`, `iso=""`, `network="nat"` | Creates and registers a new VM |
| `vbox_modify_vm` | `vm`, `cpus`, `memory_mb`, `vram_mb`, `nic`, `description`, `boot_order` | Change config (VM must be off for HW changes) |
| `vbox_clone_vm` | `source`, `name`, `mode="full"`, `snapshot=""` | `"linked"` requires a snapshot |
| `vbox_delete_vm` | `vm`, `delete_disks=false`, `confirm=false` | Needs `confirm=true`. Optionally deletes disks |
| `vbox_group_vms` | `vms[]`, `group` | Assign VMs to a group |
| `vbox_wait_for_state` | `vm`, `target_state`, `timeout_seconds=120` | Blocks until: `running`, `stopped`, `paused`, `saved`, `aborted` |

## Snapshots

| Tool | Key Params | Notes |
|------|-----------|-------|
| `vbox_snapshot_take` | `vm`, `name`, `description=""` | Works running or stopped |
| `vbox_snapshot_restore` | `vm`, `name`, `confirm=false` | Discards current state — needs `confirm=true` |
| `vbox_snapshot_delete` | `vm`, `name`, `confirm=false` | Permanent — needs `confirm=true` |
| `vbox_snapshot_rename` | `vm`, `old_name`, `new_name`, `description=""` | Rename and optionally change description |
| `vbox_snapshot_list` | `vm` | Lists all snapshots with names, UUIDs, and current indicator |

## Storage & Network

| Tool | Key Params | Notes |
|------|-----------|-------|
| `vbox_attach_iso` | `vm`, `iso_path`, `controller="sata"`, `port=1` | Mount ISO in optical drive |
| `vbox_detach_iso` | `vm`, `controller="sata"`, `port=1` | Unmount ISO |
| `vbox_shared_folder_add` | `vm`, `name`, `host_path`, `automount=true`, `readonly=false` | Share host folder (needs GA) |
| `vbox_shared_folder_remove` | `vm`, `name` | Remove shared folder |
| `vbox_nat_port_forward_add` | `vm`, `rule_name`, `protocol`, `host_port`, `guest_port`, `host_ip=""` | NAT port forwarding |
| `vbox_nat_port_forward_remove` | `vm`, `rule_name` | Remove NAT rule |
| `vbox_nat_list_rules` | `vm` | List all NAT port forwarding rules |
| `vbox_vrde_configure` | `vm`, `enabled=true`, `port=3389`, `auth_type="null"` | Configure RDP remote access |

## Disks

| Tool | Key Params | Notes |
|------|-----------|-------|
| `vbox_disk_create` | `path`, `size_mb`, `fmt="VDI"`, `variant="Standard"` | Create a new virtual disk |
| `vbox_disk_attach` | `vm`, `disk_path`, `controller="sata"`, `port=0` | Attach disk to VM |
| `vbox_disk_detach` | `vm`, `controller="sata"`, `port=0`, `confirm=false` | Detach (doesn't delete) — needs confirm |
| `vbox_disk_resize` | `disk_path`, `new_size_mb`, `confirm=false` | Grow only — irreversible. Needs confirm |
| `vbox_disk_info` | `disk_path` | Size, format, UUID, state of a disk/ISO |
| `vbox_list_media` | `media_type="disk"` | List registered media: `"disk"`, `"dvd"`, `"floppy"` |

## Host & Observability

| Tool | Key Params | Notes |
|------|-----------|-------|
| `vbox_host_info` | — | Host CPUs, RAM, OS, virtualization extensions |
| `vbox_list_ostypes` | — | Valid OS types for `vbox_create_vm` |
| `vbox_list_networks` | — | Host-only interfaces and NAT networks |
| `vbox_list_groups` | — | VM groups |
| `vbox_audit_log` | `last_n=50`, `tool_filter=""`, `result_filter=""` | Read MCP audit log |
| `vbox_audit_stats` | — | Calls per tool, errors, average duration |

## Destructive Operations (Need `confirm=true`)

- `vbox_stop_vm(mode="poweroff")`
- `vbox_reset_vm`
- `vbox_delete_vm`
- `vbox_snapshot_restore`
- `vbox_snapshot_delete`
- `vbox_disk_detach`
- `vbox_disk_resize`
