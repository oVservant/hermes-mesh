#!/usr/bin/env python3
"""
Hermes Mesh — Handshake Watcher.

Watches ~/.hermes/mesh/pending_handshake.json for new peer discoveries
and prompts the user to trust or reject them.

Usage:
    python scripts/mesh-handshake-watcher.py

Can also be imported and used programmatically:
    from mesh_handshake_watcher import HandshakeWatcher
    watcher = HandshakeWatcher()
    watcher.handle_pending(daemon)
"""

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

logger = logging.getLogger("mesh-handshake")

MESH_HOME = Path(os.environ.get("HERMES_MESH_HOME", str(Path.home() / ".hermes" / "mesh")))
SIGNAL_FILE = MESH_HOME / "pending_handshake.json"
RESPONSE_FILE = MESH_HOME / "handshake_response.json"


class HandshakeWatcher:
    """Watches for pending handshake signals and prompts the user."""

    def __init__(self):
        self._running = False
        self._last_mtime: float = 0.0
        self._handled_ids: set[str] = set()

    def start(self):
        """Start watching for handshake signals."""
        self._running = True
        logger.info("Watching for handshakes...")

        try:
            while self._running:
                if SIGNAL_FILE.exists():
                    mtime = SIGNAL_FILE.stat().st_mtime
                    if mtime != self._last_mtime:
                        self._last_mtime = mtime
                        self._process_signal()
                time.sleep(2)
        except KeyboardInterrupt:
            print("\n  Handshake watcher stopped.")

    def stop(self):
        self._running = False

    def _process_signal(self):
        try:
            data = json.loads(SIGNAL_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return

        peer_id = data.get("id", "")
        if peer_id in self._handled_ids:
            return

        self._handled_ids.add(peer_id)
        self._prompt_user(data)

    def _prompt_user(self, data: dict) -> Optional[str]:
        name = data.get("name", "unknown")
        address = data.get("address", "unknown")
        peer_id = data.get("id", "unknown")

        print(f"\n\u26a1 New peer detected: {name} @ {address}")
        print(f"  ID: {peer_id}")

        try:
            choice = input("  Trust this peer? (y/n): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            print()
            return None

        action: Optional[str] = None
        if choice in ("y", "yes"):
            action = "trust"
            print(f"  -> Peer trusted: {peer_id}")
        else:
            action = "reject"
            print(f"  -> Peer rejected: {peer_id}")

        self._write_response(peer_id, action)

        try:
            SIGNAL_FILE.unlink()
        except OSError:
            pass

        return action

    def _write_response(self, peer_id: str, action: str):
        """Write a response file that the daemon or skill can pick up."""
        data = {
            "id": peer_id,
            "action": action,
            "timestamp": time.time(),
        }
        try:
            MESH_HOME.mkdir(parents=True, exist_ok=True)
            RESPONSE_FILE.write_text(json.dumps(data, indent=2))
        except OSError as e:
            logger.error(f"Failed to write response: {e}")

    def handle_pending(self, daemon) -> Optional[str]:
        """Programmatic API: check and handle a pending handshake using a MeshDaemon instance.
        Returns 'trust', 'reject', or None if no pending handshake.
        """
        if not SIGNAL_FILE.exists():
            return None

        try:
            data = json.loads(SIGNAL_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            return None

        peer_id = data.get("id", "")
        action = self._prompt_user(data)

        if action == "trust":
            daemon.trust_peer(peer_id)

        try:
            SIGNAL_FILE.unlink()
        except OSError:
            pass

        return action


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [HANDSHAKE] %(levelname)s: %(message)s",
    )

    print("\n\u25C8 Hermes Mesh — Handshake Watcher")
    print("  Watching for new peer handshakes... (Ctrl+C to stop)\n")

    watcher = HandshakeWatcher()
    watcher.start()


if __name__ == "__main__":
    main()
