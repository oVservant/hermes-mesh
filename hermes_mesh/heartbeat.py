"""Heartbeat engine — both listener and checker."""

import asyncio
import logging
import time
from dataclasses import dataclass, field
from threading import Thread
from typing import Optional

import httpx

logger = logging.getLogger(__name__)


@dataclass
class NodeStatus:
    name: str
    address: str
    status: str = "online"  # online | busy | offline | unknown
    last_heartbeat: float = field(default_factory=time.time)
    uptime: float = 0.0
    current_task: Optional[str] = None


class HeartbeatEngine:
    """Manages heartbeat sending/receiving between mesh peers."""

    def __init__(
        self,
        agent_name: str,
        port: int = 9444,
        interval: float = 3.0,
        missed_threshold: int = 3,
        discovery=None,
    ):
        self.agent_name = agent_name
        self.port = port
        self.interval = interval
        self.missed_threshold = missed_threshold
        self.discovery = discovery
        self._known_nodes: dict[str, NodeStatus] = {}
        self._running = False
        self._thread: Optional[Thread] = None
        self._start_time = time.time()

    @property
    def uptime(self) -> float:
        return time.time() - self._start_time

    @property
    def status(self) -> str:
        return "online"

    def get_nodes(self) -> list[NodeStatus]:
        return list(self._known_nodes.values())

    def register_peer(self, name: str, address: str, heartbeat_port: int):
        """Register a peer discovered via mDNS."""
        node_id = f"{name}@{address}"
        if node_id not in self._known_nodes:
            self._known_nodes[node_id] = NodeStatus(name=name, address=address)
            logger.info(f"Registered peer: {node_id}")

    def start(self):
        self._running = True
        self._thread = Thread(target=self._loop, daemon=True)
        self._thread.start()
        logger.info(f"Heartbeat engine started on port {self.port}")

    def stop(self):
        self._running = False
        logger.info("Heartbeat engine stopped")

    def _loop(self):
        import asyncio

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self._async_loop())
        finally:
            loop.close()

    async def _async_loop(self):
        """Async heartbeat sender + receiver."""
        # Start UDP listener
        listener_task = asyncio.create_task(self._run_listener())

        while self._running:
            # Check in with known peers
            if self.discovery:
                for peer in self.discovery.get_peers():
                    self.register_peer(peer.name, peer.address, peer.heartbeat_port)

            for node_id, node in list(self._known_nodes.items()):
                try:
                    async with httpx.AsyncClient(timeout=2.0) as client:
                        resp = await client.get(
                            f"http://{node.address}:{self.port}/ping",
                            params={"name": self.agent_name},
                        )
                        if resp.status_code == 200:
                            node.last_heartbeat = time.time()
                            node.status = "online"
                except Exception:
                    if time.time() - node.last_heartbeat > self.interval * self.missed_threshold:
                        node.status = "offline"

            await asyncio.sleep(self.interval)

        listener_task.cancel()

    async def _run_listener(self):
        """Listen for incoming heartbeat pings."""
        import asyncio

        class HeartbeatProtocol(asyncio.DatagramProtocol):
            def __init__(self, engine):
                self.engine = engine

            def datagram_received(self, data, addr):
                msg = data.decode()
                if msg.startswith("PING|"):
                    parts = msg.split("|")
                    if len(parts) >= 2:
                        peer_name = parts[1]
                        # Update last seen
                        node_id = f"{peer_name}@{addr[0]}"
                        if node_id in self.engine._known_nodes:
                            self.engine._known_nodes[node_id].last_heartbeat = time.time()
                            self.engine._known_nodes[node_id].status = "online"
                        else:
                            node = NodeStatus(name=peer_name, address=addr[0])
                            self.engine._known_nodes[node_id] = node

        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            lambda: HeartbeatProtocol(self),
            local_addr=("0.0.0.0", self.port),
        )

        while self._running:
            await asyncio.sleep(1)

        transport.close()
