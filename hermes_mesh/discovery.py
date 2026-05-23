"""mDNS-based peer discovery using Zeroconf."""

import logging
import socket
import time
from dataclasses import dataclass, field
from threading import Thread
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class Peer:
    name: str
    address: str
    http_port: int
    heartbeat_port: int
    last_seen: float = field(default_factory=time.time)
    status: str = "online"  # online | busy | offline | unknown

    @property
    def id(self) -> str:
        return f"{self.name}@{self.address}"


class Discovery:
    """Peer discovery engine — currently uses simple UDP broadcast for MVP.
    Zeroconf integration planned for v0.2.
    """

    SERVICE_TYPE = "_hermes-mesh._tcp.local."
    DISCOVERY_PORT = 9445

    def __init__(self, agent_name: str, http_port: int, heartbeat_port: int):
        self.agent_name = agent_name
        self.http_port = http_port
        self.heartbeat_port = heartbeat_port
        self.peers: dict[str, Peer] = {}
        self._running = False
        self._thread: Optional[Thread] = None

    @property
    def hostname(self) -> str:
        return socket.gethostname()

    @property
    def local_ip(self) -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except OSError:
            return "127.0.0.1"

    def get_peers(self) -> list[Peer]:
        return list(self.peers.values())

    def start(self):
        self._running = True
        self._thread = Thread(target=self._discovery_loop, daemon=True)
        self._thread.start()
        logger.info(f"Discovery started — {self.agent_name} @ {self.local_ip}")

    def stop(self):
        self._running = False
        logger.info("Discovery stopped")

    def _discovery_loop(self):
        """Simple broadcast loop — sends 'who is here' and listens for responses."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.settimeout(1.0)

        try:
            sock.bind(("", self.DISCOVERY_PORT))
        except OSError:
            # Port in use — listen-only mode
            pass

        while self._running:
            try:
                # Announce
                announce = f"HELLO|{self.agent_name}|{self.local_ip}|{self.http_port}|{self.heartbeat_port}"
                sock.sendto(announce.encode(), ("255.255.255.255", self.DISCOVERY_PORT))

                # Listen for responses
                start = time.time()
                while time.time() - start < 5.0:
                    try:
                        data, addr = sock.recvfrom(1024)
                        self._handle_announce(data.decode(), addr[0])
                    except socket.timeout:
                        break

            except Exception as e:
                logger.warning(f"Discovery error: {e}")

            time.sleep(10.0)

    def _handle_announce(self, data: str, addr: str):
        if data.startswith("HELLO|"):
            parts = data.split("|")
            if len(parts) == 5:
                _, name, ip, http_port, hb_port = parts
                if name == self.agent_name:
                    return  # That's us

                peer = Peer(
                    name=name,
                    address=ip,
                    http_port=int(http_port),
                    heartbeat_port=int(hb_port),
                    last_seen=time.time(),
                )
                self.peers[peer.id] = peer
                logger.debug(f"Discovered peer: {peer.id}")
