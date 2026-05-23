<div align="center">

# ◈ Hermes Mesh

**Mesh network for Hermes Agents — auto-discovery, radar dashboard, and task delegation between agents on the same local network.**

[![Version](https://img.shields.io/badge/version-0.3.0-00ff88?style=flat-square)]()
[![Hermes Skill](https://img.shields.io/badge/hermes-skill-7c3aed?style=flat-square)]()
[![License](https://img.shields.io/badge/license-MIT-555555?style=flat-square)]()
[![PRs Welcome](https://img.shields.io/badge/PRs-welcome-brightgreen?style=flat-square)]()

---

### 🖥️ Your agents. In a network. Like they were one.

</div>

<br>

> **Hermes Mesh** converts your devices into a live mesh network of agents that discover each other, shake hands, and work together. Like a swarm. Like a band.
>
> It's a **Hermes skill** — not a service, not a framework, not a separate daemon. Load it and go.

<br>

## ⚡ What it does

| | Feature | What happens |
|---|---|---|
| 🔍 | **Auto-discovery** | Agents find each other via mDNS (Zeroconf) on the local network. No config. No IPs. |
| 🤝 | **Handshake** | First time a peer appears, you're asked to trust it. After that, automatic. |
| 💓 | **Heartbeat** | Peers ping every 3 seconds. Green = online, Red = gone. |
| 📡 | **Radar dashboard** | Open a submarine-style radar in your browser. See all nodes at a glance. |
| 🚚 | **Delegation** | Peer-to-peer via built-in HTTP server (stdlib). No Hermes API dependency. |

<br>

## 🧭 The Radar

Open `/mesh dashboard` from any agent and see your entire mesh:

<div align="center">

```
        🟢 MacBook
          \   |   /
    🔴 Windows ——— 🟢 Server
          /   |   \
        ⬤ (scanning...)
```

*A sweeping green line, glowing peer dots, status at a glance.*

</div>

<br>

## 🚀 Quick start

### 1. Install the skill

On **each** agent you want in the mesh:

```bash
hermes skills install https://raw.githubusercontent.com/oVservant/hermes-mesh/main/SKILL.md
```

Install the discovery dependency (once per machine):

```bash
pip install zeroconf
```

### 2. Load it

```bash
# In any Hermes session
/skill hermes-mesh
```

Or start the daemon directly — one command does it all (discovery, heartbeat, handshake, and task receiver):

```bash
python ~/Projects/hermes-mesh/scripts/mesh-daemon.py --name server-linux --interactive
```

When a new peer appears, you'll be prompted right there:
```
⚡ New peer detected: MacBook @ 192.168.1.11
Trust this peer? (y/n):
```

Say yes once — it's automatic forever after (TOFU).

### 3. Watch peers appear

```bash
/mesh status
/mesh peers
```

The first time a peer is detected, it'll already be in your peer list.

### 4. Open the radar

```bash
/mesh dashboard
```

Or open `dashboard/radar.html` directly in any browser.

### 5. Delegate tasks

```bash
/mesh delegate server-linux "npm run build"
/mesh broadcast "pull latest changes"
```

Or use the daemon directly for one-shot delegation:

```bash
python scripts/mesh-daemon.py --name my-agent --delegate "server-linux:build main.go"
python scripts/mesh-daemon.py --name my-agent --broadcast "run tests"
```

<br>

## 📋 Available commands

| Command | What it does |
|---|---|
| `/mesh status` | Show agent info + connected peers |
| `/mesh peers` | Detailed peer list (name, IP, status, last heartbeat) |
| `/mesh dashboard` | Open the radar in browser |
| `/mesh connect <peer_id>` | Force handshake with a peer |
| `/mesh delegate <peer_id> <task>` | Delegate a task to a specific peer |
| `/mesh broadcast <task>` | Send task to all online peers |
| `/mesh watch` | Real-time monitor mode |

<br>

## 🏗️ Architecture

```
                    ┌──────────────────┐
                    │    MacBook       │
                    │  Hermes + Mesh   │
                    └───────┬──────────┘
                            │ mDNS
              ┌─────────────┼─────────────┐
              │             │             │
              ▼             ▼             ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │    Server    │ │    Windows   │ │    Any...    │
    │  Hermes Mesh │ │  Hermes Mesh │ │   Hermes Mesh│
    └──────────────┘ └──────────────┘ └──────────────┘
```

- **Peer-to-peer.** No central server. Every agent is equal.
- **Local network only.** No internet required. No cloud dependency.
- **Zero configuration.** Discovery is fully automatic via mDNS.

<br>

## 🔒 Security model

| Level | Mechanism |
|---|---|
| **TOFU** | First encounter asks for manual approval. After that, auto-trusted. |
| **API Token** | Share a secret token between agents for authenticated requests. |
| **mTLS** | Certificate-based mutual authentication (coming in v0.4). |

Trusted peers persist in `~/.hermes/mesh/known_peers.json`.

<br>

## 📁 Project structure

```
hermes-mesh/
├── SKILL.md               ← The skill — load this into Hermes
├── README.md              ← This file
├── PRODUCT_VISION.md      ← Product vision (non-technical)
├── scripts/
│   ├── mesh-daemon.py              ← Discovery + heartbeat + handshake daemon
│   └── mesh-handshake-watcher.py   ← Watcher that prompts user to trust new peers
└── dashboard/
    └── radar.html          ← Standalone radar HTML (no server needed)
```

<br>

## 🗺️ Roadmap

- [ ] mTLS between peers for mutual authentication
- [ ] Smart routing: "run this on whoever has the most RAM"
- [ ] Skill sync across mesh agents
- [ ] Bridge mode via Tailscale for different networks
- [ ] Embdedded dashboard (instead of separate HTML)

<br>

## 🤝 Contributing

PRs welcome. Keep it simple — this project follows the **skill-first** philosophy. If it can be a script inside the skill, it should be.

<br>

---

<div align="center">

Made by [@oVservant](https://github.com/oVservant) · Hermes Mesh v0.3.0 · Skill-based · Zero-config · Peer-to-peer

</div>
