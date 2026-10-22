"""Parseo defensivo de la salida de VBoxManage."""

from __future__ import annotations

import re

_VM_RE = re.compile(r'^\s*"(?P<name>.*)"\s+\{(?P<uuid>[0-9A-Fa-f-]+)\}\s*$')
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
