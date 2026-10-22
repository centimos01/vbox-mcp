"""Parseo defensivo de la salida de VBoxManage."""

from __future__ import annotations

import re
from typing import Any

_VM_RE = re.compile(r'^\s*"(?P<name>.*?)"\s+\{(?P<uuid>[0-9A-Fa-f-]+)\}\s*$')
_KV_RE = re.compile(r"^(?P<key>[A-Za-z0-9_./\-]+)=(?P<value>.*)$")
_OSTYPE_RE = re.compile(r"^(?P<key>[^:]+):\s*(?P<value>.*)$")
_SNAPSHOT_RE = re.compile(r"^SnapshotName(?P<suffix>-\d+)?$")


def _unquote(value: str) -> str:
    value = value.strip()
    if len(value) >= 2 and value.startswith('"') and value.endswith('"'):
        value = value[1:-1]
        value = value.replace('\\"', '"').replace("\\\\", "\\")
    return value


def parse_vm_list(text: str) -> list[dict[str, str]]:
    vms: list[dict[str, str]] = []
    for line in text.splitlines():
        match = _VM_RE.match(line)
        if match:
            vms.append({"name": match.group("name"), "uuid": match.group("uuid")})
    return vms


def parse_machine_readable(text: str) -> dict[str, str]:
    data: dict[str, str] = {}
    for line in text.splitlines():
        match = _KV_RE.match(line)
        if match:
            data[match.group("key")] = _unquote(match.group("value"))
    return data


def parse_ostypes(text: str) -> list[dict[str, str]]:
    ostypes: list[dict[str, str]] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        fields: dict[str, str] = {}
        for line in block.splitlines():
            match = _OSTYPE_RE.match(line)
            if match:
                fields[match.group("key").strip().lower()] = match.group("value").strip()
        if not fields.get("id"):
            continue
        bits = "64" if fields.get("64 bit", "").lower() == "true" else "32"
        ostypes.append(
            {
                "id": fields["id"],
                "description": fields.get("description", ""),
                "family": fields.get("family desc", fields.get("family id", "")),
                "bits": bits,
            }
        )
    return ostypes


def parse_snapshots(text: str) -> list[dict[str, object]]:
    data = parse_machine_readable(text)
    current = data.get("CurrentSnapshotName")
    snapshots: list[dict[str, object]] = []
    for key in data:
        match = _SNAPSHOT_RE.match(key)
        if not match:
            continue
        suffix = match.group("suffix") or ""
        name = data[key]
        snapshots.append(
            {
                "name": name,
                "uuid": data.get(f"SnapshotUUID{suffix}", ""),
                "description": data.get(f"SnapshotDescription{suffix}", ""),
                "current": name == current,
                "timestamp": data.get(f"SnapshotTimestamp{suffix}", ""),
            }
        )
    return snapshots


def parse_blocks(text: str) -> list[dict[str, str]]:
    blocks: list[dict[str, str]] = []
    for block in re.split(r"\n\s*\n", text.strip()):
        parsed = parse_machine_readable(block)
        if parsed:
            blocks.append(parsed)
    return blocks


def parse_nat_rules(raw: dict[str, str]) -> list[dict[str, str]]:
    """Extrae las reglas NAT de la salida de showvminfo --machinereadable."""
    rules: list[dict[str, str]] = []
    for key, value in raw.items():
        if not key.startswith("Forwarding("):
            continue
        # value format: "name,protocol,host_ip,host_port,guest_ip,guest_port"
        parts = value.split(",")
        if len(parts) >= 6:
            rules.append(
                {
                    "name": parts[0],
                    "protocol": parts[1],
                    "host_ip": parts[2],
                    "host_port": parts[3],
                    "guest_ip": parts[4],
                    "guest_port": parts[5],
                }
            )
    return rules


def parse_shared_folders(raw: dict[str, str]) -> list[dict[str, object]]:
    """Extrae las carpetas compartidas de la salida de showvminfo --machinereadable."""
    folders: list[dict[str, object]] = []
    seen: set[str] = set()
    pattern = re.compile(r"^SharedFolderName(Machine|Transient)Mapping(\d+)$")
    for key, name in raw.items():
        m = pattern.match(key)
        if not m:
            continue
        kind, idx = m.group(1), m.group(2)
        if name in seen:
            continue
        seen.add(name)
        path_key = f"SharedFolderPath{kind}Mapping{idx}"
        folders.append(
            {
                "name": name,
                "host_path": raw.get(path_key, ""),
                "transient": kind == "Transient",
            }
        )
    return folders


def parse_attached_disks(raw: dict[str, str]) -> list[dict[str, object]]:
    """Extrae los discos adjuntos de la salida de showvminfo --machinereadable."""
    disks: list[dict[str, object]] = []
    # Keys like: "SATA-0-0"="path/to/disk.vdi"  and "SATA-ImageUUID-0-0"="uuid"
    medium_re = re.compile(r"^(?P<ctrl>[A-Za-z0-9]+)-(?P<port>\d+)-(?P<dev>\d+)$")
    for key, value in raw.items():
        m = medium_re.match(key)
        if not m or not value or value.lower() in {"none", "emptydrive", ""}:
            continue
        ctrl = m.group("ctrl")
        port = m.group("port")
        dev = m.group("dev")
        uuid_key = f"{ctrl}-ImageUUID-{port}-{dev}"
        disks.append(
            {
                "controller": ctrl,
                "port": int(port),
                "device": int(dev),
                "medium": value,
                "uuid": raw.get(uuid_key, ""),
            }
        )
    return disks
