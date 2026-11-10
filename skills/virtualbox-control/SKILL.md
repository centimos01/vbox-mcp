---
name: virtualbox-control
description: >
  Use when controlling VirtualBox virtual machines: taking screenshots,
  clicking UI elements, typing text, running commands inside guests,
  managing VM lifecycle, or performing any visual/interactive task
  on a VM. Activates for any task involving VirtualBox, VMs, guest OS
  interaction, or when the user asks you to do something inside a
  virtual machine.
---

# VirtualBox Autonomous Control

This skill enables you to fully control VirtualBox virtual machines — seeing the
screen, clicking, typing, running commands — everything a human user can do.

## When to Use This Skill

- Interacting visually with a VM (clicking buttons, navigating menus, filling forms)
- Installing software or configuring an OS inside a VM
- Running automated workflows inside a guest OS
- Taking screenshots to verify or monitor VM state
- Logging into a VM (Windows or Linux)
- Opening applications, navigating file explorers, using terminals
- Any task that requires "seeing" and "doing" inside a virtual machine

## The Autonomous Control Loop

**Every VM interaction follows this cycle: See → Think → Act → Verify.**

```
┌──────────────────────────────────────────────────┐
│  1. SCREENSHOT  ──→  2. ANALYZE  ──→  3. ACT     │
│       ↑                                  │       │
│       └──────────  4. VERIFY  ←──────────┘       │
└──────────────────────────────────────────────────┘
```

### Step 1: Screenshot (See)

Take a screenshot to understand the current state of the VM:

```
vbox_screenshot(vm="VM Name")
```

- **Always** screenshot BEFORE any action so you know what you're working with.
- **Always** screenshot AFTER any action to verify it worked.
- The returned PNG dimensions are the guest framebuffer resolution — these are
  the same coordinates you use for mouse clicks.

### Step 2: Analyze (Think)

Look at the screenshot and determine:

- What is currently on screen? (desktop, dialog, installer, login, error message?)
- Where are the UI elements you need to interact with? (buttons, text fields, menus)
- What pixel coordinates `(x, y)` correspond to your target?
- Is the VM ready for input, or is it still loading / processing?

### Step 3: Act (Do)

Execute the appropriate action:

| Action | Tool | Example |
|--------|------|---------|
| Click a button/icon | `vbox_mouse_click` | `vbox_mouse_click(vm, x=640, y=400)` |
| Double-click | `vbox_mouse_click` | `vbox_mouse_click(vm, x, y, double=true)` |
| Right-click | `vbox_mouse_click` | `vbox_mouse_click(vm, x, y, button="right")` |
| Type text | `vbox_send_keys` | `vbox_send_keys(vm, "hello world")` |
| Press Enter/Tab/etc. | `vbox_send_keys` | `vbox_send_keys(vm, "<enter>")` |
| Run a command | `vbox_guest_exec` | `vbox_guest_exec(vm, user, pw, exe, args)` |
| Move the mouse | `vbox_mouse_move` | `vbox_mouse_move(vm, x=100, y=200)` |

### Step 4: Verify (Confirm)

Take another screenshot to confirm the action had the desired effect.
If it didn't work, re-analyze and retry with adjusted coordinates or approach.

---

## Mouse & Coordinate System

Coordinates are in **guest framebuffer pixels** — the VM's screen resolution,
NOT the VirtualBox window size on the host.

### How to determine coordinates

1. Take a screenshot: `vbox_screenshot(vm="name")`
2. The image dimensions **are** the coordinate space (e.g., 1024×768)
3. Visually identify the target element's position in the image
4. Click at those pixel coordinates: `vbox_mouse_click(vm, x, y)`

### Coordinate tips

- **Center of screen** on 1024×768: `(512, 384)`
- **Desktop icons**: typically top-left area `(50-150, 50-150)`
- **Windows taskbar/Start**: bottom-left `(30, height-20)` on Windows
- **Linux panels**: varies — top bar or bottom bar depending on DE
- **Window title bar**: top of the window, for dragging or double-click maximize
- **Window close button (×)**: top-right corner of the window
- **Text fields**: click center to focus, then type
- **Buttons**: always aim for the **center** of the button, not the edges
- **Small elements**: be extra precise; take a new screenshot if a click misses

### Mouse operations

```
vbox_mouse_click(vm="name", x=640, y=400)                    # left click
vbox_mouse_click(vm="name", x=640, y=400, button="right")    # right click
vbox_mouse_click(vm="name", x=640, y=400, double=true)       # double click
vbox_mouse_move(vm="name", x=640, y=400)                     # move only
```

> **Requirement**: Mouse only works on Windows hosts with the VM in `mode="gui"`
> and the VirtualBox window visible in the foreground. The user must not use the
> machine while you control the mouse.

---

## Keyboard Reference

### Simple text

```
vbox_send_keys(vm="name", text="hello world")
```

### Special keys (use angle brackets)

| Keys | Token |
|------|-------|
| Enter | `<enter>` |
| Tab | `<tab>` |
| Escape | `<esc>` |
| Space | `<space>` |
| Backspace | `<backspace>` |
| Delete | `<delete>` |
| Insert | `<insert>` |
| Arrow keys | `<up>` `<down>` `<left>` `<right>` |
| Navigation | `<home>` `<end>` `<pageup>` `<pagedown>` |
| Function keys | `<f1>` through `<f12>` |

### Combined sequences

Type a username, press Tab, type a password, press Enter:

```
vbox_send_keys(vm="name", text="myuser<tab>mypassword<enter>")
```

### Methods

- `method="string"` — fast, plain ASCII only, no special key tokens
- `method="scancode"` — slower, supports `<enter>` and other tokens
- **Auto-selection**: if you include `<token>` patterns, scancode is used automatically

---

## Two Paths to VM Control

### Path A: Visual / GUI Control (No Guest Additions needed)

Use when the VM has no Guest Additions installed, or you need to interact with
graphical applications, installers, or the OS login screen.

**Tools**: `vbox_screenshot`, `vbox_mouse_click`, `vbox_mouse_move`, `vbox_send_keys`

**Pattern**: Screenshot → Find element → Click / Type → Screenshot to verify

### Path B: Guest Control (Requires Guest Additions)

Use when Guest Additions are installed and you need to run commands, transfer
files, or execute scripts inside the guest.

**Tools**: `vbox_guest_exec`, `vbox_guest_run_script`, `vbox_guest_copy_to`, `vbox_guest_copy_from`

**Pattern**: Execute command → Check stdout/stderr → React

### Path C: Combined (Best of both)

Use for complex workflows that need both visual and command-line interaction.

**Example**: Click through a GUI installer, then run configuration scripts via
`vbox_guest_exec`.

---

## Common Workflows

### Starting a VM and Taking Control

```
1. vbox_list_vms()                                          # find the VM
2. vbox_start_vm(vm="name", mode="gui")                     # MUST be "gui" for mouse!
3. vbox_wait_for_state(vm="name", target_state="running")   # wait until booted
4. (wait 15-30 seconds for the OS to finish loading)
5. vbox_screenshot(vm="name")                               # see what's on screen
```

### Logging into Windows

```
1. vbox_screenshot(vm="name")           # see lock/login screen
2. vbox_send_keys(vm, "<enter>")        # dismiss lock screen (if present)
3. (wait 2-3 seconds)
4. vbox_screenshot(vm="name")           # verify password field is visible
5. vbox_send_keys(vm, "password<enter>")
6. (wait 5-10 seconds for desktop to load)
7. vbox_screenshot(vm="name")           # verify desktop is ready
```

### Logging into Linux (GDM / SDDM / LightDM)

```
1. vbox_screenshot(vm="name")           # see login screen
2. Click on username (if visible) or type username
3. vbox_screenshot(vm="name")           # verify password field
4. vbox_send_keys(vm, "password<enter>")
5. (wait 5-10 seconds)
6. vbox_screenshot(vm="name")           # verify desktop loaded
```

### Logging into Linux TTY (no GUI)

```
1. vbox_screenshot(vm="name")
2. vbox_send_keys(vm, "username<enter>")
3. (wait 1-2 seconds)
4. vbox_send_keys(vm, "password<enter>")
5. (wait 2 seconds)
6. vbox_screenshot(vm="name")           # verify shell prompt
```

### Opening an Application

```
1. vbox_screenshot(vm="name")                        # see desktop
2. Click Start Menu / Application Launcher
3. (wait 1-2 seconds)
4. vbox_screenshot(vm="name")                        # see menu opened
5. vbox_send_keys(vm, "application name")            # search
6. (wait 1 second)
7. vbox_send_keys(vm, "<enter>")                     # launch
8. (wait 2-5 seconds)
9. vbox_screenshot(vm="name")                        # verify app opened
```

### Running a Command (With Guest Additions)

```
vbox_guest_exec(
    vm="name",
    user="myuser",
    password="mypass",
    exe="/bin/bash",
    args=["-c", "ls -la /home"]
)
```

For Windows guests:

```
vbox_guest_exec(
    vm="name",
    user="Administrator",
    password="mypass",
    exe="C:\\Windows\\System32\\cmd.exe",
    args=["/c", "dir C:\\Users"]
)
```

### Running a Command (Without Guest Additions — GUI Terminal)

```
1. Open a terminal app via the GUI workflow above
2. vbox_send_keys(vm, "ls -la /home<enter>")
3. (wait 1-2 seconds)
4. vbox_screenshot(vm, output_path="...")    # read the output
```

### Running a Multi-line Script in the Guest

```
vbox_guest_run_script(
    vm="name",
    user="myuser",
    password="mypass",
    script_content="#!/bin/bash\napt update\napt install -y nginx\nsystemctl start nginx",
    interpreter="/bin/bash",
    timeout=120
)
```

### File Transfer

```
# Host → Guest
vbox_guest_copy_to(vm, user, password, "C:\\local\\file.txt", "/home/user/file.txt")

# Guest → Host
vbox_guest_copy_from(vm, user, password, "/home/user/result.txt", "C:\\local\\result.txt")

# Recursive folder copy
vbox_guest_copy_to(vm, user, password, "C:\\project", "/home/user/project", recursive=true)
```

### Taking a Safety Snapshot Before Changes

```
1. vbox_snapshot_take(vm="name", name="before-changes")
2. ... perform risky operations ...
3. If something goes wrong:
   vbox_snapshot_restore(vm="name", name="before-changes", confirm=true)
```

### Creating a VM from Scratch

```
vbox_create_vm(
    name="ubuntu-test",
    ostype="Ubuntu24_LTS_64",
    cpus=4,
    memory_mb=8192,
    disk_mb=25600,
    iso="C:\\ISOs\\ubuntu-24.04.iso"
)
```

---

## Best Practices

### ALWAYS

- **Screenshot before AND after** every significant action
- **Wait 2-5 seconds** between actions for the VM to respond
- **Take a snapshot** before any risky or destructive operation
- Use `mode="gui"` when starting VMs you need to control visually
- **Verify each step** succeeded before proceeding to the next
- Use `vbox_wait_for_state` after starting/stopping VMs
- Prefer `vbox_guest_exec` over GUI typing when Guest Additions are available

### NEVER

- Click blindly without a **recent** screenshot
- Send rapid-fire actions without waiting for VM response
- Assume coordinates from a previous screenshot after performing actions
- Use `mode="headless"` if you need mouse/visual interaction
- Forget that the VM might be **slower** than expected (especially during boot)
- Send `confirm=true` on destructive operations without user approval

### COORDINATE ACCURACY

- Always aim for the **center** of the target element
- Buttons: click center, not edges
- Text fields: click center to focus, then start typing
- If a click doesn't work: take a **new screenshot**, recalculate, retry
- For very small elements: consider using keyboard navigation instead

### TIMING GUIDELINES

| Situation | Wait Time |
|-----------|-----------|
| After VM boot | 15-30 seconds |
| After login | 5-10 seconds |
| After clicking a button | 1-3 seconds |
| After typing text | 0.5-1 second |
| During installations | 5-15 seconds between steps |
| After opening an app | 2-5 seconds |
| After a heavy operation | 5-10 seconds |

### ERROR RECOVERY

- **Screen looks wrong**: take a fresh screenshot and re-evaluate
- **Click missed target**: re-screenshot, recalculate coordinates, retry
- **VM seems frozen**: try `vbox_send_keys(vm, "<esc>")` or just screenshot to check
- **Totally stuck**: snapshot current state, then try an alternative approach
- **Guest Additions not working**: fall back to GUI-only control (Path A)
- **Window lost focus**: the tool will error; the user may need to click the VBox window
- **Dialog box appeared**: screenshot, handle the dialog first, then continue

---

## Requirements & Limitations

- **VirtualBox 7.x** must be installed on the host
- **Mouse control**: Windows host ONLY, VM in GUI mode, VBox window visible and in foreground
- **Guest Control**: Guest Additions must be installed and running inside the VM
- `VBOX_MCP_ALLOW_MOUSE=true` (this is the default)
- **Do NOT use the host machine** while the AI controls the mouse
- Screenshots and keyboard work for all VMs (running, not saved); mouse requires GUI mode
- Shared folders added while the VM is running are transient (disappear on shutdown)

---

## Tools Quick Reference

Read `references/tools-quick-ref.md` for a complete table of all 43 available
MCP tools with their parameters.
