from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEARTBEAT_FILE = ROOT / "data" / "sync-heartbeat.json"
HEARTBEAT_INTERVAL = timedelta(days=7)


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc)


def heartbeat_is_due(path: Path, now: datetime) -> bool:
    if not path.exists():
        return True

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        updated_at = parse_timestamp(payload["updatedAt"])
    except (KeyError, TypeError, ValueError, json.JSONDecodeError):
        return True

    return now - updated_at >= HEARTBEAT_INTERVAL


def update_heartbeat(path: Path = HEARTBEAT_FILE, now: datetime | None = None) -> bool:
    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    if not heartbeat_is_due(path, current_time):
        print("Scheduler heartbeat is still current.")
        return False

    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "updatedAt": current_time.isoformat().replace("+00:00", "Z"),
        "purpose": "Keeps scheduled result synchronization active during quiet periods.",
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Updated scheduler heartbeat at {payload['updatedAt']}.")
    return True


if __name__ == "__main__":
    update_heartbeat()
