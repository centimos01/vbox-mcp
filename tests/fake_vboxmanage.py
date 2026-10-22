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

    touch_index = response.get("touch_index")
    if touch_index is not None:
        from pathlib import Path

        target = Path(args[int(touch_index)])
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\x0dIHDR" + (800).to_bytes(4, "big") + (600).to_bytes(4, "big"))
    return int(response.get("returncode", 0))


if __name__ == "__main__":
    raise SystemExit(main())
