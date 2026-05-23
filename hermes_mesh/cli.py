"""CLI entry point for Hermes Mesh."""

import argparse
import logging
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="Hermes Mesh — Agent Mesh Network")
    parser.add_argument("--host", default="0.0.0.0", help="Host to bind (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=None, help="HTTP port (default: from config)")
    parser.add_argument("--config", type=Path, default=None, help="Path to config.toml")
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )

    # Set config path env var before importing app
    if args.config:
        import os
        os.environ["HERMES_MESH_HOME"] = str(args.config.parent)

    import uvicorn
    from .config import load_config

    config = load_config(args.config)
    port = args.port or config.mesh.http_port

    print(f"◈ Hermes Mesh v0.1.0")
    print(f"  Agent:    {config.mesh.agent_name}")
    print(f"  HTTP:     http://{args.host}:{port}")
    print(f"  Dashboard: http://{args.host}:{port}/")
    print(f"  Status:   http://{args.host}:{port}/status")
    print()

    uvicorn.run(
        "hermes_mesh.api:app",
        host=args.host,
        port=port,
        log_level="info",
        reload=args.debug,
    )


if __name__ == "__main__":
    main()
