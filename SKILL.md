---
name: hermes-mesh
description: "Mesh network for Hermes Agents: auto-discovery, heartbeat, handshake, task delegation, and automated task execution with result callbacks between agents on the same local network."
version: 0.4.0
author: oVservant
tags: [mesh, discovery, delegation, multi-agent, networking, real-time]
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
6. **Task Watcher** — las tareas se ejecutan automáticamente sin intervención manual
7. **Callback** — el peer destino devuelve el resultado al origen apenas termina

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

### Flow completo (v0.4)

Cuando delegás una tarea con `/mesh delegate server-linux "build main.go"`:

1. Se busca el peer `server-linux` en la lista de peers conocidos
2. Se genera un `task_id` único (UUID4) y se incluye el `callback_address` del origen
3. Se manda un POST a `http://{peer.address}:{peer.mesh_port}/execute`
4. El peer destino recibe la tarea y la escribe en `~/.hermes/mesh/pending_tasks.json`
5. **NUEVO**: El **task watcher** (thread integrado en el daemon) detecta la tarea y la ejecuta automáticamente
6. **NUEVO**: Al terminar, el resultado se guarda en `~/.hermes/mesh/completed_tasks.json`
7. **NUEVO**: Se hace callback automático via `POST /result` al origen con el output
8. La tarea ejecutada se limpia de `pending_tasks.json`

Esto significa que **no tenés que avisarle al agente** que revise sus tareas — se ejecutan solas,
y el agente que delegó recibe el resultado automáticamente.

### Endpoints HTTP

| Endpoint | Método | Descripción |
|---|---|---|
| `/status` | GET | Estado del mesh: peers, tareas, stats |
| `/results` | GET | Resultados de tareas completadas. Query: `?task_id=xxx` para filtrar |
| `/execute` | POST | Recibir una tarea delegada (body: `{command, task_id, callback_address}`) |
| `/result` | POST | Recibir resultado de una tarea completada (body: `{task_id, success, output, error}`) |

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
│   ├── mesh-daemon.py              ← Daemon: discovery mDNS, heartbeat, HTTP server, task watcher, handshake
│   └── mesh-handshake-watcher.py   ← Watcher de handshakes standalone (alternativa a --interactive)
└── dashboard/
    └── radar.html                  ← Radar HTML autocontenido
```

### Archivos de datos (en ~/.hermes/mesh/)

| Archivo | Propósito |
|---|---|
| `known_peers.json` | Peers confiables (persistencia) |
| `pending_tasks.json` | Tareas delegadas pendientes de ejecución |
| `completed_tasks.json` | Resultados de tareas ya ejecutadas |
| `agent_status.json` | Estado del agente local (busy/online) |
| `pending_handshake.json` | Handshakes nuevos esperando confirmación |

## Próximos pasos (roadmap)

- [x] ~~Task watcher automático + callback de resultados~~ (v0.4)
- [ ] mTLS entre peers para autenticación mutua
- [ ] Routing inteligente: "ejecutá esto en el que tenga más RAM"
- [ ] Sync de skills entre agents del mesh
- [ ] Modo bridge vía Tailscale para redes distintas
- [ ] Dashboard embebido en vez de HTML separado
- [ ] Cola de tareas con reintentos si el peer origen está offline al momento del callback
