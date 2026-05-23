---
name: hermes-mesh
description: "Mesh network for Hermes Agents: auto-discovery, heartbeat, handshake, and task delegation between agents on the same local network."
version: 0.2.0
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

Cuando se detecta un peer nuevo, el skill pregunta:

> *"Se detectó [MacBook] en la red (192.168.1.11). ¿Querés conectarlo al mesh?"*

Si aceptás, intercambia tokens de confianza. La próxima vez que aparezca, se conecta automáticamente (TOFU — Trust On First Use).

Los peers confiables se guardan en `~/.hermes/mesh/known_peers.json`.

## Delegación entre agentes

La delegación usa la API HTTP interna de Hermes Agent (la misma que usa `delegate_task`). No levanta servidores extra.

Cuando decís `/mesh delegate server-linux "build main.go"`, el skill:

1. Busca el peer `server-linux` en la lista de peers conocidos
2. Se conecta a su API Hermes vía HTTP
3. Delega la tarea
4. Te devuelve el resultado

Si el peer está offline, te avisa y no insiste.

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
│   └── mesh-daemon.py        ← Daemon de discovery mDNS + heartbeat + handshake
└── dashboard/
    └── radar.html            ← Radar HTML autocontenido
```

## Próximos pasos (roadmap)

- [ ] mTLS entre peers para autenticación mutua
- [ ] Routing inteligente: \"ejecutá esto en el que tenga más RAM\"
- [ ] Sync de skills entre agents del mesh
- [ ] Modo bridge vía Tailscale para redes distintas
- [ ] Dashboard embebido en vez de HTML separado
