"""Config loader for Hermes Mesh from TOML file."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

try:
    import tomllib
except ImportError:
    import tomli as tomllib

import os


@dataclass
class MeshConfig:
    agent_name: str = "server-linux"
    http_port: int = 9443
    heartbeat_port: int = 9444
    heartbeat_interval: float = 3.0
    missed_heartbeat_threshold: int = 3
    discovery_interval: float = 30.0
    task_timeout: int = 300


@dataclass
class DashboardConfig:
    enabled: bool = True
    theme: str = "dark"


@dataclass
class SecurityConfig:
    trust_on_first_use: bool = True
    cert_validity_days: int = 365
    cert_renew_days: int = 7


@dataclass
class Config:
    mesh: MeshConfig = field(default_factory=MeshConfig)
    dashboard: DashboardConfig = field(default_factory=DashboardConfig)
    security: SecurityConfig = field(default_factory=SecurityConfig)


def load_config(path: Optional[Path] = None) -> Config:
    """Load config from TOML file, using defaults where not specified."""
    if path is None:
        path = Path(os.environ.get("HERMES_MESH_HOME", str(Path.home() / ".hermes" / "mesh-agent-b"))) / "config.toml"

    config = Config()

    if path.exists():
        data = tomllib.loads(path.read_text())

        if "mesh" in data:
            m = data["mesh"]
            config.mesh = MeshConfig(
                agent_name=m.get("agent_name", config.mesh.agent_name),
                http_port=m.get("http_port", config.mesh.http_port),
                heartbeat_port=m.get("heartbeat_port", config.mesh.heartbeat_port),
                heartbeat_interval=m.get("heartbeat_interval", config.mesh.heartbeat_interval),
                missed_heartbeat_threshold=m.get("missed_heartbeat_threshold", config.mesh.missed_heartbeat_threshold),
                discovery_interval=m.get("discovery_interval", config.mesh.discovery_interval),
                task_timeout=m.get("task_timeout", config.mesh.task_timeout),
            )

        if "dashboard" in data:
            d = data["dashboard"]
            config.dashboard = DashboardConfig(
                enabled=d.get("enabled", config.dashboard.enabled),
                theme=d.get("theme", config.dashboard.theme),
            )

        if "security" in data:
            s = data["security"]
            config.security = SecurityConfig(
                trust_on_first_use=s.get("trust_on_first_use", config.security.trust_on_first_use),
                cert_validity_days=s.get("cert_validity_days", config.security.cert_validity_days),
                cert_renew_days=s.get("cert_renew_days", config.security.cert_renew_days),
            )

    return config
