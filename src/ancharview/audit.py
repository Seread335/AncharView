from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path


_LOCK = threading.Lock()
_ACTIONS = {"click", "set_text"}
_EVENT_STATUSES = {
    "request": {"pending"},
    "consent": {"approved", "declined", "cancelled", "unavailable"},
    "action": {"started", "succeeded", "failed"},
}


def audit_log_path() -> Path:
    configured_path = os.environ.get("ANCHARVIEW_AUDIT_PATH")
    if configured_path:
        return Path(configured_path).expanduser()
    return Path.home() / ".ancharview" / "audit.jsonl"


def write_audit_event(event: str, action: str, element_id: str, status: str) -> None:
    if action not in _ACTIONS or status not in _EVENT_STATUSES.get(event, set()):
        raise ValueError("Unsupported audit event.")

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z"),
        "event": event,
        "action": action,
        "element_id": element_id[:128],
        "status": status,
    }
    line = json.dumps(entry, ensure_ascii=False, separators=(",", ":")) + "\n"
    path = audit_log_path()
    is_default_path = not os.environ.get("ANCHARVIEW_AUDIT_PATH")

    with _LOCK:
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700 if is_default_path else 0o755)
        if is_default_path and os.name != "nt":
            os.chmod(path.parent, 0o700)

        descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "a", encoding="utf-8") as audit_file:
            audit_file.write(line)
            audit_file.flush()
            os.fsync(audit_file.fileno())

        if os.name != "nt":
            os.chmod(path, 0o600)