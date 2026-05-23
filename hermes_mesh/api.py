"""FastAPI application for Hermes Mesh."""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import load_config, Config
from .discovery import Discovery
from .heartbeat import HeartbeatEngine

_config: Optional[Config] = None
_discovery: Optional[Discovery] = None
_heartbeat: Optional[HeartbeatEngine] = None


def get_config() -> Config:
    global _config
    if _config is None:
        _config = load_config()
    return _config


def get_discovery() -> Discovery | None:
    global _discovery
    return _discovery


def get_heartbeat() -> HeartbeatEngine | None:
    global _heartbeat
    return _heartbeat


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _config, _discovery, _heartbeat
    _config = load_config()

    _discovery = Discovery(
        agent_name=_config.mesh.agent_name,
        http_port=_config.mesh.http_port,
        heartbeat_port=_config.mesh.heartbeat_port,
    )
    _heartbeat = HeartbeatEngine(
        agent_name=_config.mesh.agent_name,
        port=_config.mesh.heartbeat_port,
        interval=_config.mesh.heartbeat_interval,
        missed_threshold=_config.mesh.missed_heartbeat_threshold,
        discovery=_discovery,
    )

    _discovery.start()
    _heartbeat.start()

    yield

    _heartbeat.stop()
    _discovery.stop()


app = FastAPI(title="Hermes Mesh", version="0.1.0", lifespan=lifespan)

# Mount static files
STATIC_DIR = Path(__file__).parent / "static"
STATIC_DIR.mkdir(exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/status")
async def status():
    cfg = get_config()
    hb = get_heartbeat()
    disc = get_discovery()

    return {
        "agent": cfg.mesh.agent_name,
        "version": "0.1.0",
        "uptime_seconds": hb.uptime,
        "status": hb.status,
        "local_ip": disc.local_ip,
        "http_port": cfg.mesh.http_port,
        "heartbeat_port": cfg.mesh.heartbeat_port,
        "peers": [
            {
                "name": node.name,
                "address": node.address,
                "status": node.status,
                "last_heartbeat": node.last_heartbeat,
            }
            for node in hb.get_nodes()
        ],
        "discovered": [
            {"name": p.name, "address": p.address, "last_seen": p.last_seen}
            for p in disc.get_peers()
        ],
    }


@app.get("/ping")
async def ping(name: str = "unknown"):
    """Heartbeat ping endpoint."""
    return JSONResponse({"pong": True, "agent": get_config().mesh.agent_name, "peer": name})


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Render the radar dashboard."""
    return DASHBOARD_HTML


DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Hermes Mesh — Radar</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #0a0a0f;
            color: #00ff88;
            font-family: 'Courier New', monospace;
            overflow: hidden;
            height: 100vh;
            display: flex;
            flex-direction: column;
        }
        #header {
            padding: 16px 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid #1a2a1a;
        }
        #header h1 { font-size: 18px; letter-spacing: 2px; }
        #header .status-dot {
            width: 10px; height: 10px;
            border-radius: 50%;
            background: #00ff88;
            box-shadow: 0 0 8px #00ff88;
            animation: pulse 2s infinite;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.3; }
        }
        #canvas-container {
            flex: 1;
            position: relative;
        }
        canvas { display: block; }
        #legend {
            position: absolute;
            bottom: 20px;
            left: 20px;
            display: flex;
            gap: 20px;
            font-size: 12px;
        }
        .legend-item { display: flex; align-items: center; gap: 6px; }
        .legend-dot {
            width: 8px; height: 8px;
            border-radius: 50%;
        }
        .legend-dot.online { background: #00ff88; box-shadow: 0 0 6px #00ff88; }
        .legend-dot.busy { background: #ffaa00; box-shadow: 0 0 6px #ffaa00; }
        .legend-dot.offline { background: #ff3333; box-shadow: 0 0 6px #ff3333; }
        .legend-dot.unknown { background: #555555; }
        #info-panel {
            position: absolute;
            top: 20px;
            right: 20px;
            background: rgba(0,0,0,0.7);
            border: 1px solid #1a3a1a;
            padding: 12px 16px;
            font-size: 12px;
            line-height: 1.6;
            border-radius: 4px;
            min-width: 200px;
        }
    </style>
</head>
<body>
    <div id="header">
        <h1>◈ HERMES MESH RADAR</h1>
        <div class="status-dot" id="status-dot"></div>
    </div>
    <div id="canvas-container">
        <canvas id="radar"></canvas>
        <div id="legend">
            <div class="legend-item"><span class="legend-dot online"></span> Online</div>
            <div class="legend-item"><span class="legend-dot busy"></span> Busy</div>
            <div class="legend-item"><span class="legend-dot offline"></span> Offline</div>
            <div class="legend-item"><span class="legend-dot unknown"></span> Unknown</div>
        </div>
        <div id="info-panel">
            <div id="agent-name">Loading...</div>
            <div id="agent-ip"></div>
            <div id="agent-uptime"></div>
            <div id="peer-count"></div>
        </div>
    </div>
    <script>
        const canvas = document.getElementById('radar');
        const ctx = canvas.getContext('2d');

        let peers = [];
        let sweepAngle = 0;
        let selfInfo = {};

        function resize() {
            canvas.width = canvas.parentElement.clientWidth;
            canvas.height = canvas.parentElement.clientHeight;
        }
        window.addEventListener('resize', resize);
        resize();

        async function fetchStatus() {
            try {
                const resp = await fetch('/status');
                const data = await resp.json();
                selfInfo = data;
                peers = data.peers;

                document.getElementById('agent-name').textContent = 'Agent: ' + data.agent;
                document.getElementById('agent-ip').textContent = 'IP: ' + data.local_ip + ':' + data.http_port;
                document.getElementById('agent-uptime').textContent = 'Uptime: ' + Math.floor(data.uptime_seconds) + 's';
                document.getElementById('peer-count').textContent = 'Peers: ' + peers.length;

                document.getElementById('status-dot').style.background =
                    peers.length > 0 ? '#00ff88' : '#555555';
            } catch(e) {
                console.warn('Status fetch failed:', e);
            }
        }

        function draw() {
            ctx.clearRect(0, 0, canvas.width, canvas.height);

            const cx = canvas.width / 2;
            const cy = canvas.height / 2;
            const radius = Math.min(cx, cy) * 0.7;

            // Radar grid
            ctx.strokeStyle = '#0a2a0a';
            ctx.lineWidth = 1;
            for (let r = radius/3; r <= radius; r += radius/3) {
                ctx.beginPath();
                ctx.arc(cx, cy, r, 0, Math.PI * 2);
                ctx.stroke();
            }

            // Cross hairs
            ctx.strokeStyle = '#0a2a0a';
            ctx.beginPath();
            ctx.moveTo(cx - radius, cy); ctx.lineTo(cx + radius, cy);
            ctx.moveTo(cx, cy - radius); ctx.lineTo(cx, cy + radius);
            ctx.stroke();

            // Sweep line
            sweepAngle += 0.02;
            ctx.strokeStyle = 'rgba(0, 255, 136, 0.4)';
            ctx.lineWidth = 2;
            ctx.beginPath();
            ctx.moveTo(cx, cy);
            ctx.lineTo(
                cx + Math.cos(sweepAngle) * radius,
                cy + Math.sin(sweepAngle) * radius
            );
            ctx.stroke();

            // Sweep glow
            const gradient = ctx.createRadialGradient(cx, cy, 0, cx, cy, radius);
            gradient.addColorStop(0, 'rgba(0, 255, 136, 0.15)');
            gradient.addColorStop(0.4, 'rgba(0, 255, 136, 0.05)');
            gradient.addColorStop(1, 'rgba(0, 0, 0, 0)');

            ctx.fillStyle = gradient;
            ctx.beginPath();
            const sweepStart = sweepAngle - 0.15;
            const sweepEnd = sweepAngle + 0.15;
            ctx.moveTo(cx, cy);
            ctx.arc(cx, cy, radius, sweepStart, sweepEnd);
            ctx.closePath();
            ctx.fill();

            // Center dot (self)
            ctx.fillStyle = '#00ff88';
            ctx.shadowColor = '#00ff88';
            ctx.shadowBlur = 15;
            ctx.beginPath();
            ctx.arc(cx, cy, 6, 0, Math.PI * 2);
            ctx.fill();
            ctx.shadowBlur = 0;

            // Peer nodes
            peers.forEach((peer, i) => {
                const angle = (i / Math.max(peers.length, 1)) * Math.PI * 2 + sweepAngle * 0.3;
                const dist = radius * 0.7;
                const px = cx + Math.cos(angle) * dist;
                const py = cy + Math.sin(angle) * dist;

                let color;
                switch(peer.status) {
                    case 'online': color = '#00ff88'; break;
                    case 'busy': color = '#ffaa00'; break;
                    case 'offline': color = '#ff3333'; break;
                    default: color = '#555555';
                }

                ctx.fillStyle = color;
                ctx.shadowColor = color;
                ctx.shadowBlur = peer.status === 'online' ? 10 : 4;
                ctx.beginPath();
                ctx.arc(px, py, 5, 0, Math.PI * 2);
                ctx.fill();
                ctx.shadowBlur = 0;

                // Label
                ctx.fillStyle = color;
                ctx.font = '10px "Courier New"';
                ctx.fillText(peer.name, px + 10, py + 4);
                ctx.fillText(peer.address, px + 10, py + 16);
            });

            requestAnimationFrame(draw);
        }

        fetchStatus();
        setInterval(fetchStatus, 3000);
        draw();
    </script>
</body>
</html>"""
