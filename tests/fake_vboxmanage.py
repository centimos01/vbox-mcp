"""VBoxManage falso para tests: registra llamadas y devuelve respuestas."""

from __future__ import annotations

import json
import os
import sys


def main() -> int:
    log_path = os.environ["FAKE_VBOX_LOG"]
    config_path = os.environ.get("FAKE_VBOX_CONFIG")

    args = sys.argv[1:]
    with open(log_path, "a", encoding="utf-8") as fh:
        fh.write(json.dumps({"args": args}, ensure_ascii=False) + "\n")

    responses: dict[str, dict] = {}
    if config_path and os.path.exists(config_path):
        with open(config_path, encoding="utf-8") as fh:
            responses = json.load(fh)

    key = " ".join(args)
    response = responses.get(key) or responses.get("default") or {}

    sys.stdout.buffer.write(str(response.get("stdout", "")).encode("utf-8"))
    sys.stderr.buffer.write(str(response.get("stderr", "")).encode("utf-8"))
    return int(response.get("returncode", 0))


if __name__ == "__main__":
    raise SystemExit(main())
