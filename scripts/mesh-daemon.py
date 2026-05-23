#!/usr/bin/env python3
"""
Hermes Mesh — Discovery + Heartbeat + Handshake daemon.
Uses Zeroconf (mDNS) for peer discovery. No external server needed.

Usage:
    python mesh-daemon.py [--name SERVER-LINUX] [--api-port 8080]
"""

import argparse
import json
import logging
import os
import socket
import sys
import time
import uuid
from dataclasses import dataclass, field, asdict
from pathlib import Path
from threading import Thread, Lock
from typing import Optional

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [MESH] %(levelname)s: %(message)s",
)
logger = logging.getLogger("mesh")

# ── Try importing zeroconf ──────────────────────────────────────────────

try:
    from zeroconf import ServiceInfo, ServiceBrowser, Zeroconf, ServiceStateChange
    HAS_ZEROCONF = True
except ImportError:
    HAS_ZEROCONF = False
    logger.warning("zeroconf not installed — falling back to UDP broadcast")
    logger.warning("Install: pip install zeroconf")


# ── Config ──────────────────────────────────────────────────────────────

MESH_HOME = Path(os.environ.get("HERMES_MESH_HOME", str(Path.home() / ".hermes" / "mesh")))
KNOWN_PEERS_PATH = MESH_HOME / "known_peers.json"
SERVICE_TYPE = "_hermes-mesh._tcp.local."
DISCOVERY_PORT = 9445
HEARTBEAT_INTERVAL = 3.0
MISSED_THRESHOLD = 3


# ── Data types ──────────────────────────────────────────────────────────

@dataclass
class Peer:
    name: str
    address: str
    api_port: int = 8080
    status: str = "online"     # online | busy | offline
    last_seen: float = field(default_factory=time.time)
    trusted: bool = False       # TOFU — accepted manually first time
    capabilities: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return f"{self.name}@{self.address}"


@dataclass
class SelfInfo:
    name: str
    address: str
    api_port: int
    capabilities: list[str]


# ── Mesh Daemon ─────────────────────────────────────────────────────────

class MeshDaemon:
    """Runs discovery, heartbeat, and handshake in background threads."""

    def __init__(self, agent_name: str, api_port: int, capabilities: list[str] = None):
        self.self_info = SelfInfo(
            name=agent_name,
            address=self._get_local_ip(),
            api_port=api_port,
            capabilities=capabilities or [],
        )
        self.peers: dict[str, Peer] = {}
        self._lock = Lock()
        self._running = False
        self._zeroconf: Optional[Zeroconf] = None
        self._service_info: Optional[ServiceInfo] = None
        self._threads: list[Thread] = []

        MESH_HOME.mkdir(parents=True, exist_ok=True)
        self._load_known_peers()

    # ── Public API ──────────────────────────────────────────────────

    def start(self):
        """Start discovery + heartbeat threads."""
        self._running = True

        if HAS_ZEROCONF:
            self._threads.append(Thread(target=self._zeroconf_register, daemon=True))
            self._threads.append(Thread(target=self._zeroconf_browse, daemon=True))
        else:
            self._threads.append(Thread(target=self._udp_discovery_loop, daemon=True))

        self._threads.append(Thread(target=self._heartbeat_loop, daemon=True))

        for t in self._threads:
            t.start()

        logger.info(f"Mesh started — {self.self_info.name} @ {self.self_info.address}:{self.self_info.api_port}")
        return self

    def stop(self):
        self._running = False
        if self._zeroconf:
            self._zeroconf.close()
        self._save_known_peers()
        logger.info("Mesh stopped")

    def get_peers(self, status_filter: str = None) -> list[Peer]:
        with self._lock:
            peers = list(self.peers.values())
        if status_filter:
            peers = [p for p in peers if p.status == status_filter]
        return sorted(peers, key=lambda p: p.name)

    def get_peer(self, peer_id: str) -> Optional[Peer]:
        with self._lock:
            return self.peers.get(peer_id)

    def get_trusted_peers(self) -> list[Peer]:
        return [p for p in self.get_peers() if p.trusted]

    def trust_peer(self, peer_id: str) -> bool:
        with self._lock:
            if peer_id in self.peers:
                self.peers[peer_id].trusted = True
                self._save_known_peers()
                return True
        return False

    def get_status_summary(self) -> dict:
        peers = self.get_peers()
        return {
            "agent": self.self_info.name,
            "address": self.self_info.address,
            "api_port": self.self_info.api_port,
            "peers_total": len(peers),
            "peers_online": len([p for p in peers if p.status == "online"]),
            "peers_trusted": len([p for p in peers if p.trusted]),
            "peers": [{"id": p.id, "name": p.name, "address": p.address, "status": p.status, "trusted": p.trusted}
                      for p in peers],
        }

    # ── Zeroconf (mDNS) ────────────────────────────────────────────

    def _zeroconf_register(self):
        """Register our service so others can find us."""
        self._zeroconf = Zeroconf()

        service_name = f"{self.self_info.name}.{SERVICE_TYPE}"
        local_ip = socket.inet_aton(self.self_info.address)

        self._service_info = ServiceInfo(
            type_=SERVICE_TYPE,
            name=service_name,
            addresses=[local_ip],
            port=self.self_info.api_port,
            properties={
                "name": self.self_info.name,
                "version": "0.2.0",
                "capabilities": ",".join(self.self_info.capabilities),
            },
        )
        self._zeroconf.register_service(self._service_info)
        logger.info(f"mDNS registered as {service_name}")

        while self._running:
            time.sleep(30)

    def _zeroconf_browse(self):
        """Browse for other Hermes Mesh services."""
        while not self._zeroconf:
            time.sleep(0.5)

        browser = ServiceBrowser(self._zeroconf, SERVICE_TYPE, handlers=[self._on_service_change])

        while self._running:
            time.sleep(10)

    def _on_service_change(self, zeroconf, service_type, name, state_change):
        if state_change == ServiceStateChange.Added:
            info = zeroconf.get_service_info(service_type, name)
            if info and info.parsed_addresses():
                peer_name = info.properties.get(b"name", b"unknown").decode()
                if peer_name == self.self_info.name:
                    return  # That's us

                peer = Peer(
                    name=peer_name,
                    address=info.parsed_addresses()[0],
                    api_port=info.port,
                    capabilities=info.properties.get(b"capabilities", b"").decode().split(",") if info.properties.get(b"capabilities") else [],
                    last_seen=time.time(),
                )

                # Check if already known
                existing = self.get_peer(peer.id)
                if existing and existing.trusted:
                    peer.trusted = True

                with self._lock:
                    self.peers[peer.id] = peer

                if existing and existing.trusted:
                    logger.info(f"Peer reconnected: {peer.id}")
                else:
                    logger.info(f"New peer discovered: {peer.id}")
                    self._on_new_peer(peer)

    # ── UDP fallback (when zeroconf not available) ──────────────────

    def _udp_discovery_loop(self):
        """UDP broadcast-based discovery — fallback when mDNS unavailable."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(1.0)

        try:
            sock.bind(("", DISCOVERY_PORT))
        except OSError:
            pass

        while self._running:
            try:
                announce = f"HERMES-MESH|{self.self_info.name}|{self.self_info.address}|{self.self_info.api_port}|{','.join(self.self_info.capabilities)}"
                sock.sendto(announce.encode(), ("255.255.255.255", DISCOVERY_PORT))

                start = time.time()
                while time.time() - start < 5.0:
                    try:
                        data, addr = sock.recvfrom(1024)
                        self._handle_udp_announce(data.decode(), addr[0])
                    except socket.timeout:
                        break
            except Exception as e:
                logger.warning(f"UDP discovery error: {e}")

            time.sleep(10.0)

    def _handle_udp_announce(self, data: str, addr: str):
        if data.startswith("HERMES-MESH|"):
            parts = data.split("|")
            if len(parts) >= 4:
                _, name, ip, api_port = parts[:4]
                capabilities = parts[4].split(",") if len(parts) > 4 and parts[4] else []
                if name == self.self_info.name:
                    return

                peer = Peer(
                    name=name,
                    address=ip,
                    api_port=int(api_port),
                    capabilities=capabilities,
                    last_seen=time.time(),
                )

                existing = self.get_peer(peer.id)
                if existing and existing.trusted:
                    peer.trusted = True

                with self._lock:
                    self.peers[peer.id] = peer

                if existing and existing.trusted:
                    logger.info(f"Peer reconnected (UDP): {peer.id}")
                else:
                    logger.info(f"New peer discovered (UDP): {peer.id}")
                    self._on_new_peer(peer)

    # ── Heartbeat ──────────────────────────────────────────────────

    def _heartbeat_loop(self):
        """Periodically check that known peers are still alive."""
        while self._running:
            time.sleep(HEARTBEAT_INTERVAL)
            with self._lock:
                for peer_id, peer in list(self.peers.items()):
                    if time.time() - peer.last_seen > HEARTBEAT_INTERVAL * MISSED_THRESHOLD:
                        if peer.status != "offline":
                            peer.status = "offline"
                            logger.info(f"Peer went offline: {peer_id}")

            # Prune peers that have been offline for > 60s
            with self._lock:
                for peer_id, peer in list(self.peers.items()):
                    if peer.status == "offline" and time.time() - peer.last_seen > 60:
                        if not peer.trusted:
                            del self.peers[peer_id]
                            logger.info(f"Pruned untrusted offline peer: {peer_id}")

    # ── New peer handler ───────────────────────────────────────────

    def _on_new_peer(self, peer: Peer):
        """Called when a new (untrusted) peer is discovered.
        The skill's handshake handler will prompt the user to trust them.
        """
        # Signal file for the skill to pick up
        signal_path = MESH_HOME / "pending_handshake.json"
        signal_path.write_text(json.dumps({
            "name": peer.name,
            "address": peer.address,
            "api_port": peer.api_port,
            "id": peer.id,
            "timestamp": time.time(),
        }))

    # ── Persistence ────────────────────────────────────────────────

    def _load_known_peers(self):
        if KNOWN_PEERS_PATH.exists():
            try:
                data = json.loads(KNOWN_PEERS_PATH.read_text())
                with self._lock:
                    for entry in data:
                        peer = Peer(
                            name=entry["name"],
                            address=entry["address"],
                            api_port=entry.get("api_port", 8080),
                            trusted=True,
                            capabilities=entry.get("capabilities", []),
                        )
                        self.peers[peer.id] = peer
                logger.info(f"Loaded {len(data)} known peers")
            except Exception as e:
                logger.warning(f"Failed to load known peers: {e}")

    def _save_known_peers(self):
        trusted = [p for p in self.get_peers() if p.trusted]
        data = [
            {"name": p.name, "address": p.address, "api_port": p.api_port, "capabilities": p.capabilities}
            for p in trusted
        ]
        KNOWN_PEERS_PATH.parent.mkdir(parents=True, exist_ok=True)
        KNOWN_PEERS_PATH.write_text(json.dumps(data, indent=2))
        logger.info(f"Saved {len(trusted)} trusted peers")

    # ── Utils ──────────────────────────────────────────────────────

    @staticmethod
    def _get_local_ip() -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except OSError:
            return "127.0.0.1"


# ── CLI ─────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Hermes Mesh Daemon")
    parser.add_argument("--name", default=socket.gethostname(), help="Agent name")
    parser.add_argument("--api-port", type=int, default=8080, help="Hermes API port")
    parser.add_argument("--capabilities", default="", help="Comma-separated capabilities")
    parser.add_argument("--debug", action="store_true", help="Debug logging")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger("mesh").setLevel(logging.DEBUG)

    caps = [c.strip() for c in args.capabilities.split(",") if c.strip()]

    daemon = MeshDaemon(
        agent_name=args.name,
        api_port=args.api_port,
        capabilities=caps,
    )

    daemon.start()

    print(f"\n◈ Hermes Mesh v0.2.0")
    print(f"  Agent:    {daemon.self_info.name}")
    print(f"  Address:  {daemon.self_info.address}")
    print(f"  API port: {daemon.self_info.api_port}")
    print(f"  Peers:    {len(daemon.get_peers())} known")
    print(f"\n  Watching for peers... (Ctrl+C to stop)\n")

    try:
        while True:
            time.sleep(10)
            peers = daemon.get_peers()
            online = [p for p in peers if p.status == "online"]
            trusted = [p for p in peers if p.trusted]
            print(f"  [{time.strftime('%H:%M:%S')}] {len(online)} online / {len(trusted)} trusted / {len(peers)} total")

            # Check for pending handshakes
            signal_path = MESH_HOME / "pending_handshake.json"
            if signal_path.exists():
                try:
                    handshake = json.loads(signal_path.read_text())
                    print(f"\n  ⚡ New peer detected: {handshake['name']} @ {handshake['address']}")
                    print(f"     Run: /mesh connect {handshake['id']}")
                    signal_path.unlink()
                except Exception:
                    pass

    except KeyboardInterrupt:
        print("\n  Shutting down...")
    finally:
        daemon.stop()


if __name__ == "__main__":
    main()
