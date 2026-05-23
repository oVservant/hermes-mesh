---
name: hermes-mesh
description: "Mesh network for Hermes Agents: auto-discovery, heartbeat, handshake, and task delegation between agents on the same local network."
version: 0.3.0
author: oVservant
tags: [mesh, discovery, delegation, multi-agent, networking]
---

# Hermes Mesh

Conecta tus Hermes Agents en red local. Se descubren solos, hacen handshake, y podés delegar tareas entre ellos sin pensar en IPs ni config manual.

## Cómo funciona

Cuando cargás el skill en un Hermes Agent, automáticamente:

1. **Anuncia** tu presencia en la red local vía mDNS (Zeroconf)
2. **Escucha** anuncios de otros agentes Hermes
3. **Handshake** — pregunta si querés conectar al peer detectado
4. **Heartbeat** — cada nodo manda ping cada 3s para saber quién está vivo
5. **Delegación** — podés mandar tareas a cualquier peer conectado

No necesita servicios externos, no necesita puertos abiertos, no necesita internet.

## Instalación

```bash
# Desde el repo
hermes skills install https://raw.githubusercontent.com/oVservant/hermes-mesh/main/SKILL.md

# O manual, clonando
git clone https://github.com/oVservant/hermes-mesh.git ~/Projects/hermes-mesh
# Y en sesión: /skill hermes-mesh
```

Dependencias del script de discovery:

```bash
pip install zeroconf
```

## Uso

### Con el flag interactivo (recomendado)

Un solo comando hace todo — discovery, heartbeat, handshake y server de delegación:

```bash
python scripts/mesh-daemon.py --name my-agent --interactive
```

Cuando un peer nuevo aparece, te pregunta ahí mismo:

```
⚡ New peer detected: MacBook @ 192.168.1.11
Trust this peer? (y/n):
```

Decís que sí una vez, y de ahí en más se reconecta automáticamente (TOFU).

### Modo silencioso + watcher separado

Si preferís separar el daemon del handshake:

```bash
# Terminal 1: daemon
python scripts/mesh-daemon.py --name my-agent

# Terminal 2: handshake watcher
python scripts/mesh-handshake-watcher.py
```

### Delegación one-shot desde CLI

```bash
# Delegar a un peer específico
python scripts/mesh-daemon.py --name my-agent --delegate "server-linux@192.168.1.10:build main.go"

# Broadcast a todos los peers online
python scripts/mesh-daemon.py --name my-agent --broadcast "run tests"
```

### Desde Hermes (con el skill cargado)

```bash
/mesh status
/mesh peers
/mesh dashboard
/mesh delegate server-linux "npm run build"
/mesh broadcast "pull latest changes"
/mesh watch
```

## Comandos

Una vez cargado el skill, usás estos comandos en tu sesión de Hermes:

| Comando | Descripción |
|---|---|
| `/mesh status` | Estado del mesh: agente actual + peers conectados |
| `/mesh peers` | Lista detallada de peers detectados (nombre, IP, estado, último heartbeat) |
| `/mesh dashboard` | Abre el radar HTML en el browser |
| `/mesh connect <peer_id>` | Forzar handshake con un peer específico |
| `/mesh delegate <peer_id> <task>` | Delegar una tarea a un peer |
| `/mesh broadcast <task>` | Mandar tarea a todos los peers online |
| `/mesh watch` | Modo monitor: muestra updates en tiempo real de peers que aparecen/desaparecen |

## Discovery automático (mDNS)

El skill usa Zeroconf (Avahi/mDNS) para descubrir peers. Cada agente se anuncia como:

```
_hermes-mesh._tcp.local.
```

Con los siguientes TXT records:
- `name` — nombre del agente
- `version` — versión de Hermes Mesh
- `capabilities` — qué puede hacer (build, test, browser, etc.)

Los peers aparecen solos. No hay que configurar nada.

## Handshake

Cuando se detecta un peer nuevo, el daemon:

**Con `--interactive`:** pregunta ahí mismo si querés confiar.
**Sin `--interactive`:** escribe `~/.hermes/mesh/pending_handshake.json` y espera que el watcher (o el skill) lo lea.

### Handshake flow (end-to-end)

1. **Daemon** descubre un peer nuevo vía mDNS y escribe `pending_handshake.json`
2. El **thread interactivo** (o `mesh-handshake-watcher.py`) lo detecta
3. Prompt: *"⚡ New peer detected: {name} @ {address}"*
4. En **y** (trust): peer se guarda en `known_peers.json` → confiable
5. En **n** (reject): peer se descarta
6. La próxima vez que aparezca, se reconecta automáticamente (TOFU)

Los peers confiables se guardan en `~/.hermes/mesh/known_peers.json`.

## Delegación entre agentes (peer-to-peer)

El daemon levanta un mini-server HTTP en el puerto `--mesh-port` (default 9445) usando
solo `http.server` de stdlib. No depende de la API de Hermes Agent — es peer-to-peer directo.

Cuando delegás una tarea con `/mesh delegate server-linux "build main.go"`:

1. Se busca el peer `server-linux` en la lista de peers conocidos
2. Se manda un POST a `http://{peer.address}:{peer.mesh_port}/execute`
3. El peer destino recibe la tarea y la escribe en `~/.hermes/mesh/pending_tasks.json`
4. Hermes (o un watcher de tareas) la recoge y la ejecuta

También podés usar el daemon directamente por CLI:

```bash
# Delegar a un peer específico
python scripts/mesh-daemon.py --name my-agent --delegate "server-linux@192.168.1.10:build main.go"

# Broadcast a todos los peers online
python scripts/mesh-daemon.py --name my-agent --broadcast "run tests"
```

## Dashboard (radar)

El radar es un HTML autocontenido que podés abrir en cualquier browser. Muestra:

- Barrido tipo radar militar
- Nodos con colores según estado (🟢 online, 🟡 busy, 🔴 offline)
- Labels con nombre e IP
- Auto-refresh cada 3 segundos

Se abre con `/mesh dashboard` o directamente abriendo `dashboard/radar.html`.

## Seguridad

Por defecto, la red local es el límite de confianza (solo se descubren peers en la misma subred). Para capas extra:

| Nivel | Qué hace |
|---|---|
| **TOFU** | Primer peer se acepta manual, después automático |
| **API Token** | Compartir un token entre agentes para autenticar requests |
| **mTLS** | Intercambio de certificados entre peers (próxima versión) |

## Estructura del proyecto

```
hermes-mesh/
├── SKILL.md                  ← Este archivo, el skill que se carga en Hermes
├── PRODUCT_VISION.md         ← Documento de visión del producto
├── scripts/
│   ├── mesh-daemon.py              ← Daemon de discovery mDNS + heartbeat + HTTP server + handshake
│   └── mesh-handshake-watcher.py   ← Watcher de handshakes standalone (alternativa a --interactive)
└── dashboard/
    └── radar.html                  ← Radar HTML autocontenido
```

## Próximos pasos (roadmap)

- [ ] mTLS entre peers para autenticación mutua
- [ ] Routing inteligente: "ejecutá esto en el que tenga más RAM"
- [ ] Sync de skills entre agents del mesh
- [ ] Modo bridge vía Tailscale para redes distintas
- [ ] Dashboard embebido en vez de HTML separado
