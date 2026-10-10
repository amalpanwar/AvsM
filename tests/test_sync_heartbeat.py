from __future__ import annotations

import json
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from scripts.update_sync_heartbeat import HEARTBEAT_INTERVAL, update_heartbeat


class SyncHeartbeatTests(unittest.TestCase):
    def test_creates_missing_heartbeat(self):
        now = datetime(2026, 10, 10, 15, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sync-heartbeat.json"

            self.assertTrue(update_heartbeat(path, now))
            self.assertEqual(json.loads(path.read_text())["updatedAt"], "2026-10-10T15:00:00Z")

    def test_does_not_rewrite_current_heartbeat(self):
        now = datetime(2026, 10, 10, 15, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sync-heartbeat.json"
            update_heartbeat(path, now)

            self.assertFalse(update_heartbeat(path, now + HEARTBEAT_INTERVAL - timedelta(seconds=1)))
            self.assertEqual(json.loads(path.read_text())["updatedAt"], "2026-10-10T15:00:00Z")

    def test_rewrites_expired_heartbeat(self):
        now = datetime(2026, 10, 10, 15, 0, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "sync-heartbeat.json"
            update_heartbeat(path, now)

            self.assertTrue(update_heartbeat(path, now + HEARTBEAT_INTERVAL))
            self.assertEqual(json.loads(path.read_text())["updatedAt"], "2026-10-17T15:00:00Z")


if __name__ == "__main__":
    unittest.main()
