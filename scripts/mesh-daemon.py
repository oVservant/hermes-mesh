#!/usr/bin/env python3
"""
Hermes Mesh — Discovery + Heartbeat + Handshake + Delegation daemon.
Uses Zeroconf (mDNS) for peer discovery. No external server needed.

Runs discovery threads, heartbeat, and a lightweight HTTP server for
receiving delegated tasks from peers. Delegation is direct peer-to-peer
using the daemon's own HTTP server — no Hermes API dependency.

Usage:
    python mesh-daemon.py [--name SERVER-LINUX] [--mesh-port 9445] [--interactive]
"""

import argparse
import json
import logging
import os
import signal
import socket
import subprocess
import sys
import time
import uuid
from dataclasses import dataclass, field
from http.server import HTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from threading import Thread, Lock
from typing import Optional
from urllib.request import Request, urlopen
from urllib.error import URLError

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
MESH_VERSION = "0.4.0"
TASK_RESULTS_PATH = MESH_HOME / "task_results.json"
COMPLETED_TASKS_PATH = MESH_HOME / "completed_tasks.json"
TASK_WATCHER_INTERVAL = 2.0  # seconds between polls for pending tasks


# ── Data types ──────────────────────────────────────────────────────────

@dataclass
class Peer:
    name: str
    address: str
    mesh_port: int = 9445
    status: str = "online"     # online | busy | offline
    last_seen: float = field(default_factory=time.time)
    trusted: bool = False       # TOFU — accepted manually first time
    capabilities: list = field(default_factory=list)

    @property
    def id(self) -> str:
        return f"{self.name}@{self.address}"


@dataclass
class SelfInfo:
    name: str
    address: str
    mesh_port: int
    capabilities: list


# ── HTTP Server for receiving delegated tasks ────────────────────────────

class MeshHTTPHandler(BaseHTTPRequestHandler):
    """Lightweight server that receives delegated tasks from peers."""

    daemon: Optional["MeshDaemon"] = None  # set by the factory

    def log_message(self, format, *args):
        logger.debug(f"HTTP: {args[0]}")

    def do_GET(self):
        if self.path == "/status":
            summary = self.daemon.get_status_summary()
            self._json_response(200, summary)
        elif self.path.startswith("/results"):
            # /results?task_id=xxx or /results (all)
            task_id = None
            qs = self.path.split("?", 1)[-1] if "?" in self.path else ""
            for part in qs.split("&"):
                if part.startswith("task_id="):
                    task_id = part.split("=", 1)[1]
            results = self.daemon.get_task_results(task_id)
            self._json_response(200, {"results": results})
        else:
            self._json_response(404, {"error": "not found"})

    def do_POST(self):
        if self.path == "/execute":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._json_response(400, {"error": "invalid JSON"})
                return

            command = data.get("command", "")
            task_id = data.get("task_id", str(uuid.uuid4()))
            from_peer = data.get("from_peer", "unknown")
            callback_address = data.get("callback_address", "")

            task_entry = {
                "command": command,
                "task_id": task_id,
                "from_peer": from_peer,
                "callback_address": callback_address,
                "received_at": time.time(),
            }

            # Store in pending tasks file — task watcher picks it up automatically
            pending_tasks_path = MESH_HOME / "pending_tasks.json"
            self.daemon._with_lock_write_json(pending_tasks_path, task_entry)

            logger.info(f"Received task {task_id} from {from_peer}: {command[:80]}")
            self._json_response(200, {"status": "accepted", "task_id": task_id})

        elif self.path == "/result":
            content_length = int(self.headers.get("Content-Length", 0))
            body = self.rfile.read(content_length)
            try:
                data = json.loads(body)
            except json.JSONDecodeError:
                self._json_response(400, {"error": "invalid JSON"})
                return

            task_id = data.get("task_id", "unknown")
            success = data.get("success", False)
            output = data.get("output", "")
            error = data.get("error", "")
            from_peer = data.get("from_peer", "unknown")

            result_entry = {
                "task_id": task_id,
                "success": success,
                "output": output,
                "error": error,
                "from_peer": from_peer,
                "received_at": time.time(),
            }
            self.daemon._store_result(task_id, result_entry)
            logger.info(f"Received result for task {task_id} from {from_peer}: success={success}")
            self._json_response(200, {"status": "received", "task_id": task_id})

        else:
            self._json_response(404, {"error": "not found"})

    def _json_response(self, code: int, data: dict):
        body = json.dumps(data).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _make_handler(daemon: "MeshDaemon"):
    """Factory to inject daemon reference into the handler."""
    class Handler(MeshHTTPHandler):
        pass
    Handler.daemon = daemon
    return Handler


# ── Mesh Daemon ─────────────────────────────────────────────────────────

class MeshDaemon:
    """Runs discovery, heartbeat, handshake, and delegation in background threads."""

    def __init__(
        self,
        agent_name: str,
        mesh_port: int = 9445,
        capabilities: list = None,
        interactive: bool = False,
    ):
        self.interactive = interactive
        self.self_info = SelfInfo(
            name=agent_name,
            address=self._get_local_ip(),
            mesh_port=mesh_port,
            capabilities=capabilities or [],
        )
        self.peers: dict = {}
        self._lock = Lock()
        self._running = False
        self._zeroconf: Optional[Zeroconf] = None
        self._service_info: Optional[ServiceInfo] = None
        self._http_server: Optional[HTTPServer] = None
        self._threads: list = []

        MESH_HOME.mkdir(parents=True, exist_ok=True)
        self._load_known_peers()

    # ── Public API ──────────────────────────────────────────────────

    def start(self):
        """Start all threads: discovery, heartbeat, HTTP server, handshake (optional)."""
        self._running = True

        # HTTP task receiver
        handler = _make_handler(self)
        self._http_server = HTTPServer(("0.0.0.0", self.self_info.mesh_port), handler)
        self._threads.append(Thread(target=self._run_http_server, daemon=True))

        if HAS_ZEROCONF:
            self._threads.append(Thread(target=self._zeroconf_register, daemon=True))
            self._threads.append(Thread(target=self._zeroconf_browse, daemon=True))
        else:
            self._threads.append(Thread(target=self._udp_discovery_loop, daemon=True))

        self._threads.append(Thread(target=self._heartbeat_loop, daemon=True))
        self._threads.append(Thread(target=self._task_watcher_thread, daemon=True))

        if self.interactive:
            self._threads.append(Thread(target=self._handshake_thread, daemon=True))

        for t in self._threads:
            t.start()

        logger.info(
            f"Mesh started — {self.self_info.name} @ {self.self_info.address}:{self.self_info.mesh_port}"
        )
        return self

    def stop(self):
        self._running = False
        if self._zeroconf:
            self._zeroconf.close()
        if self._http_server:
            self._http_server.shutdown()
        self._save_known_peers()
        logger.info("Mesh stopped")

    def get_peers(self, status_filter: str = None) -> list:
        with self._lock:
            peers = list(self.peers.values())
        if status_filter:
            peers = [p for p in peers if p.status == status_filter]
        return sorted(peers, key=lambda p: p.name)

    def get_peer(self, peer_id: str) -> Optional[Peer]:
        with self._lock:
            return self.peers.get(peer_id)

    def get_trusted_peers(self) -> list:
        return [p for p in self.get_peers() if p.trusted]

    def trust_peer(self, peer_id: str) -> bool:
        with self._lock:
            if peer_id in self.peers:
                self.peers[peer_id].trusted = True
                self._save_known_peers()
                return True
        return False

    def reject_peer(self, peer_id: str):
        with self._lock:
            self.peers.pop(peer_id, None)

    def mark_self_busy(self):
        """Mark the local agent as busy (used when a task is received)."""
        with self._lock:
            pass  # Status is per-peer, self doesn't have a peer entry
        # Signal file that Hermes skill can read
        busy_path = MESH_HOME / "agent_status.json"
        busy_path.write_text(json.dumps({"status": "busy", "updated": time.time()}))

    def mark_self_idle(self):
        idle_path = MESH_HOME / "agent_status.json"
        idle_path.write_text(json.dumps({"status": "online", "updated": time.time()}))

    def get_status_summary(self) -> dict:
        peers = self.get_peers()
        return {
            "agent": self.self_info.name,
            "address": self.self_info.address,
            "mesh_port": self.self_info.mesh_port,
            "peers_total": len(peers),
            "peers_online": len([p for p in peers if p.status == "online"]),
            "peers_trusted": len([p for p in peers if p.trusted]),
            "peers": [
                {
                    "id": p.id,
                    "name": p.name,
                    "address": p.address,
                    "status": p.status,
                    "trusted": p.trusted,
                }
                for p in peers
            ],
        }

    # ── Delegation (outgoing) ────────────────────────────────────

    def delegate_task(self, peer_id: str, task_description: str, timeout: int = 300) -> dict:
        """Send a task to a specific peer's mesh HTTP server.

        Includes callback_address so the receiving peer can POST results back
        to /result on this daemon when the task completes.
        """
        peer = self.get_peer(peer_id)
        if not peer:
            return {"success": False, "error": f"Peer not found: {peer_id}"}
        if peer.status == "offline":
            return {"success": False, "error": f"Peer is offline: {peer_id}"}

        task_id = str(uuid.uuid4())
        callback_address = f"{self.self_info.address}:{self.self_info.mesh_port}"

        url = f"http://{peer.address}:{peer.mesh_port}/execute"
        payload = {
            "command": task_description,
            "from_peer": self.self_info.name,
            "task_id": task_id,
            "callback_address": callback_address,
            "timeout": timeout,
        }
        body = json.dumps(payload).encode()
        req = Request(url, data=body, headers={"Content-Type": "application/json"})

        try:
            resp = urlopen(req, timeout=10)
            result = json.loads(resp.read().decode())
            return {"success": True, "peer": peer_id, "task_id": task_id, "result": result}
        except URLError as e:
            return {
                "success": False,
                "peer": peer_id,
                "task_id": task_id,
                "error": str(e.reason if hasattr(e, "reason") else e),
            }

    def broadcast_task(self, task_description: str, timeout: int = 300) -> list:
        """Send a task to all online trusted peers."""
        results = []
        for peer in self.get_trusted_peers():
            if peer.status == "online":
                results.append(self.delegate_task(peer.id, task_description, timeout))
        return results

    # ── HTTP server thread ──────────────────────────────────────

    def _run_http_server(self):
        logger.info(f"Task receiver listening on :{self.self_info.mesh_port}")
        while self._running:
            try:
                self._http_server.handle_request()
            except Exception as e:
                if self._running:
                    logger.warning(f"HTTP server error: {e}")
                time.sleep(0.5)

    # ── Zeroconf (mDNS) ────────────────────────────────────────

    def _zeroconf_register(self):
        """Register our service so others can find us."""
        self._zeroconf = Zeroconf()
        service_name = f"{self.self_info.name}.{SERVICE_TYPE}"
        local_ip = socket.inet_aton(self.self_info.address)

        self._service_info = ServiceInfo(
            type_=SERVICE_TYPE,
            name=service_name,
            addresses=[local_ip],
            port=self.self_info.mesh_port,
            properties={
                "name": self.self_info.name,
                "version": MESH_VERSION,
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

        ServiceBrowser(self._zeroconf, SERVICE_TYPE, handlers=[self._on_service_change])

        while self._running:
            time.sleep(1)

    def _on_service_change(self, zeroconf, service_type, name, state_change):
        if state_change == ServiceStateChange.Added:
            info = zeroconf.get_service_info(service_type, name)
            if info and info.parsed_addresses():
                peer_name = info.properties.get(b"name", b"unknown").decode()
                if peer_name == self.self_info.name:
                    return

                peer = Peer(
                    name=peer_name,
                    address=info.parsed_addresses()[0],
                    mesh_port=info.port,
                    capabilities=(
                        info.properties.get(b"capabilities", b"")
                        .decode()
                        .split(",")
                        if info.properties.get(b"capabilities")
                        else []
                    ),
                    last_seen=time.time(),
                )

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

        elif state_change == ServiceStateChange.Removed:
            peer_name = name.replace(f".{SERVICE_TYPE}", "")
            with self._lock:
                for peer_id, peer in list(self.peers.items()):
                    if peer.name == peer_name:
                        peer.status = "offline"
                        logger.info(f"Peer removed via mDNS: {peer_id}")
                        break

    # ── UDP fallback ──────────────────────────────────────────────────

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
                announce = (
                    f"HERMES-MESH|{self.self_info.name}|{self.self_info.address}"
                    f"|{self.self_info.mesh_port}|{','.join(self.self_info.capabilities)}"
                )
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
                _, name, ip, mesh_port = parts[:4]
                capabilities = parts[4].split(",") if len(parts) > 4 and parts[4] else []
                if name == self.self_info.name:
                    return

                peer = Peer(
                    name=name,
                    address=ip,
                    mesh_port=int(mesh_port),
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
        """Check known peers are alive; also send heartbeat pings."""
        while self._running:
            time.sleep(HEARTBEAT_INTERVAL)

            # Ping trusted peers via their /status endpoint
            for peer in self.get_trusted_peers():
                try:
                    url = f"http://{peer.address}:{peer.mesh_port}/status"
                    resp = urlopen(url, timeout=2)
                    if resp.status == 200:
                        with self._lock:
                            if peer.id in self.peers:
                                self.peers[peer.id].last_seen = time.time()
                                if self.peers[peer.id].status == "offline":
                                    self.peers[peer.id].status = "online"
                                    logger.info(f"Peer came back online: {peer.id}")
                except Exception:
                    pass

            # Detect dead peers
            with self._lock:
                for peer_id, peer in list(self.peers.items()):
                    if time.time() - peer.last_seen > HEARTBEAT_INTERVAL * MISSED_THRESHOLD:
                        if peer.status != "offline":
                            peer.status = "offline"
                            logger.info(f"Peer went offline: {peer_id}")

            # Prune untrusted offline peers
            with self._lock:
                for peer_id, peer in list(self.peers.items()):
                    if peer.status == "offline" and time.time() - peer.last_seen > 60:
                        if not peer.trusted:
                            del self.peers[peer_id]
                            logger.info(f"Pruned untrusted offline peer: {peer_id}")

    # ── Handshake (built-in, runs as thread when --interactive) ────

    def _handshake_thread(self):
        """Watch for new peers and prompt the user to trust them."""
        logger.info("Handshake watcher started — you'll be prompted for new peers")
        seen_handshakes = set()

        while self._running:
            signal_path = MESH_HOME / "pending_handshake.json"
            if signal_path.exists():
                try:
                    data = json.loads(signal_path.read_text())
                    peer_id = data.get("id", "")
                    if peer_id not in seen_handshakes:
                        name = data.get("name", "unknown")
                        address = data.get("address", "unknown")
                        print(f"\n  ⚡ New peer detected: {name} @ {address}")
                        try:
                            choice = input("  Trust this peer? (y/n): ").strip().lower()
                        except (EOFError, KeyboardInterrupt):
                            print()
                            break
                        if choice in ("y", "yes"):
                            self.trust_peer(peer_id)
                            print(f"  -> Peer trusted: {peer_id}")
                        else:
                            self.reject_peer(peer_id)
                            print(f"  -> Peer rejected: {peer_id}")
                        seen_handshakes.add(peer_id)
                    signal_path.unlink()
                except Exception:
                    pass
            time.sleep(2)

    # ── New peer handler ───────────────────────────────────────────

    def _on_new_peer(self, peer: Peer):
        """Write signal file for handshake (picked up by interactive thread or external watcher)."""
        signal_path = MESH_HOME / "pending_handshake.json"
        signal_path.write_text(
            json.dumps(
                {
                    "name": peer.name,
                    "address": peer.address,
                    "mesh_port": peer.mesh_port,
                    "id": peer.id,
                    "timestamp": time.time(),
                }
            )
        )

    # ── Task Watcher ───────────────────────────────────────────────

    def _task_watcher_thread(self):
        """Watch pending_tasks.json and execute any new tasks automatically."""
        logger.info("Task watcher started — executing pending tasks automatically")
        seen_task_ids: set = set()

        while self._running:
            pending_path = MESH_HOME / "pending_tasks.json"
            if pending_path.exists():
                try:
                    data = json.loads(pending_path.read_text())
                    if not isinstance(data, list):
                        data = []
                    tasks = data
                except (json.JSONDecodeError, FileNotFoundError):
                    tasks = []

                for task_id in list(seen_task_ids):
                    if not any(t.get("task_id") == task_id for t in tasks):
                        seen_task_ids.discard(task_id)

                for task in tasks:
                    tid = task.get("task_id", "")
                    if tid in seen_task_ids:
                        continue
                    seen_task_ids.add(tid)

                    logger.info(f"Executing task {tid}: {task.get('command', '')[:80]}")
                    success, output, error = self._execute_task(task)

                    # Store result locally
                    self._store_result(tid, {
                        "task_id": tid,
                        "success": success,
                        "output": output,
                        "error": error,
                        "command": task.get("command", ""),
                        "from_peer": task.get("from_peer", "unknown"),
                        "completed_at": time.time(),
                    })

                    # Send callback to origin peer if callback_address is set
                    callback_address = task.get("callback_address", "")
                    if callback_address:
                        self._send_callback(tid, callback_address, success, output, error)

                # Remove executed tasks from pending
                if tasks:
                    self._remove_pending_tasks([t.get("task_id", "") for t in tasks])

            time.sleep(TASK_WATCHER_INTERVAL)

    def _execute_task(self, task: dict) -> tuple:
        """Execute a shell command. Returns (success, stdout, stderr)."""
        command = task.get("command", "")
        timeout = task.get("timeout", 300)
        try:
            result = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                cwd=str(Path.home()),
            )
            success = result.returncode == 0
            output = result.stdout.strip()
            error = result.stderr.strip() if not success else ""
            if not success and not error:
                error = f"exit code {result.returncode}"
            return success, output, error
        except subprocess.TimeoutExpired:
            return False, "", f"Task timed out after {timeout}s"
        except Exception as e:
            return False, "", str(e)

    def _store_result(self, task_id: str, entry: dict):
        """Store a task result in completed_tasks.json."""
        with self._lock:
            existing = []
            if COMPLETED_TASKS_PATH.exists():
                try:
                    existing = json.loads(COMPLETED_TASKS_PATH.read_text())
                    if not isinstance(existing, list):
                        existing = []
                except (json.JSONDecodeError, FileNotFoundError):
                    existing = []
            # Update if exists, otherwise append
            found = False
            for i, item in enumerate(existing):
                if item.get("task_id") == task_id:
                    existing[i] = entry
                    found = True
                    break
            if not found:
                existing.append(entry)
            COMPLETED_TASKS_PATH.write_text(json.dumps(existing, indent=2))

    def _send_callback(self, task_id: str, callback_address: str,
                       success: bool, output: str, error: str):
        """Send task result back to the originating peer."""
        payload = {
            "task_id": task_id,
            "success": success,
            "output": output,
            "error": error,
            "from_peer": self.self_info.name,
        }
        body = json.dumps(payload).encode()
        req = Request(
            f"http://{callback_address}/result",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        try:
            resp = urlopen(req, timeout=5)
            if resp.status == 200:
                logger.info(f"Callback sent for task {task_id} to {callback_address}")
            else:
                logger.warning(f"Callback for task {task_id} to {callback_address} returned {resp.status}")
        except Exception as e:
            logger.warning(f"Failed to send callback for task {task_id} to {callback_address}: {e}")

    def _remove_pending_tasks(self, task_ids: list):
        """Remove executed tasks from pending_tasks.json."""
        pending_path = MESH_HOME / "pending_tasks.json"
        with self._lock:
            if not pending_path.exists():
                return
            try:
                data = json.loads(pending_path.read_text())
                if not isinstance(data, list):
                    data = []
            except (json.JSONDecodeError, FileNotFoundError):
                return
            filtered = [t for t in data if t.get("task_id", "") not in task_ids]
            if len(filtered) != len(data):
                pending_path.write_text(json.dumps(filtered, indent=2))
                logger.debug(f"Cleaned up {len(data) - len(filtered)} completed tasks from pending")

    def get_task_results(self, task_id: Optional[str] = None) -> list:
        """Return completed task results, optionally filtered by task_id."""
        if not COMPLETED_TASKS_PATH.exists():
            return []
        try:
            results = json.loads(COMPLETED_TASKS_PATH.read_text())
            if not isinstance(results, list):
                return []
        except (json.JSONDecodeError, FileNotFoundError):
            return []
        if task_id:
            return [r for r in results if r.get("task_id") == task_id]
        return results

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
                            mesh_port=entry.get("mesh_port", 9445),
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
            {
                "name": p.name,
                "address": p.address,
                "mesh_port": p.mesh_port,
                "capabilities": p.capabilities,
            }
            for p in trusted
        ]
        KNOWN_PEERS_PATH.parent.mkdir(parents=True, exist_ok=True)
        KNOWN_PEERS_PATH.write_text(json.dumps(data, indent=2))
        logger.info(f"Saved {len(trusted)} trusted peers")

    def _with_lock_write_json(self, path: Path, entry: dict):
        """Thread-safe JSON append to a file (simple last-write-wins for tasks)."""
        with self._lock:
            existing = []
            if path.exists():
                try:
                    existing = json.loads(path.read_text())
                    if not isinstance(existing, list):
                        existing = []
                except (json.JSONDecodeError, FileNotFoundError):
                    existing = []
            existing.append(entry)
            path.write_text(json.dumps(existing, indent=2))

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
    parser.add_argument(
        "--mesh-port",
        type=int,
        default=9445,
        help="Port for peer-to-peer task delegation (default: 9445)",
    )
    parser.add_argument(
        "--capabilities",
        default="",
        help="Comma-separated capabilities",
    )
    parser.add_argument(
        "--delegate",
        default="",
        help="Delegate a one-shot task: 'peer_id:task description'",
    )
    parser.add_argument(
        "--broadcast",
        default="",
        help="Broadcast a one-shot task to all online trusted peers",
    )
    parser.add_argument(
        "--interactive",
        action="store_true",
        help="Prompt for handshake confirmations directly (no separate watcher needed)",
    )
    parser.add_argument("--debug", action="store_true", help="Debug logging")
    args = parser.parse_args()

    if args.debug:
        logging.getLogger("mesh").setLevel(logging.DEBUG)

    caps = [c.strip() for c in args.capabilities.split(",") if c.strip()]

    daemon = MeshDaemon(
        agent_name=args.name,
        mesh_port=args.mesh_port,
        capabilities=caps,
        interactive=args.interactive,
    )

    daemon.start()

    # One-shot delegation mode
    if args.delegate:
        if ":" not in args.delegate:
            print("  Usage: --delegate \"peer_id:task description\"")
            daemon.stop()
            return
        peer_id, task = args.delegate.split(":", 1)
        print(f"\n  Delegating task to {peer_id}...")
        result = daemon.delegate_task(peer_id.strip(), task.strip())
        print(f"  Result: {json.dumps(result, indent=2)}")
        daemon.stop()
        return

    if args.broadcast:
        print("\n  Broadcasting task to all online trusted peers...")
        results = daemon.broadcast_task(args.broadcast.strip())
        for r in results:
            status = "OK" if r["success"] else "FAIL"
            detail = r.get("result", r.get("error", "unknown"))
            print(f"  [{r['peer']}] {status}: {detail}")
        daemon.stop()
        return

    print(f"\n◈ Hermes Mesh v{MESH_VERSION}")
    print(f"  Agent:       {daemon.self_info.name}")
    print(f"  Address:     {daemon.self_info.address}")
    print(f"  Mesh port:   {daemon.self_info.mesh_port}")
    print(f"  Peers:       {len(daemon.get_peers())} known")
    if args.interactive:
        print(f"  Handshake:   interactive (you'll be prompted)")
    print(f"\n  Watching for peers... (Ctrl+C to stop)\n")

    try:
        while True:
            time.sleep(10)
            peers = daemon.get_peers()
            online = [p for p in peers if p.status == "online"]
            trusted = [p for p in peers if p.trusted]
            timestamp = time.strftime("%H:%M:%S")
            print(f"  [{timestamp}] {len(online)} online / {len(trusted)} trusted / {len(peers)} total")

            # Show pending handshakes if NOT interactive (interactive mode handles them)
            if not args.interactive:
                signal_path = MESH_HOME / "pending_handshake.json"
                if signal_path.exists():
                    try:
                        handshake = json.loads(signal_path.read_text())
                        print(f"\n  ⚡ New peer detected: {handshake['name']} @ {handshake['address']}")
                        print(f"     Run with --interactive or start mesh-handshake-watcher.py to trust it")
                        signal_path.unlink()
                    except Exception:
                        pass

    except KeyboardInterrupt:
        print("\n  Shutting down...")
    finally:
        daemon.stop()


if __name__ == "__main__":
    main()
