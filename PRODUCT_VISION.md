# Hermes Mesh — Visión de Producto

## Tagline

**Tus agentes, en red. Como si fueran uno solo.**

---

## El problema

Tenés tres dispositivos con Hermes Agent corriendo: una laptop Windows, una MacBook, y un server Linux. Cada uno tiene sus fortalezas — el server para tareas pesadas, la MacBook para desarrollo, la laptop Windows para testing. Pero hoy, para usar esa capacidad distribuida, tenés que:

- Saberte las IPs de memoria
- Conectarte por SSH manualmente
- Copiar archivos de un lado a otro
- Coordinar "a mano" qué hace cada uno

**Tus agentes no se conocen entre sí.** Están aislados, cada uno en su mundo, cuando en realidad forman parte de un mismo equipo.

---

## La visión

**Hermes Mesh** convierte tus dispositivos en una red viva de agentes que se descubren, se reconocen, y trabajan juntos. Como un enjambre. Como una banda.

Cuando entrás a tu red WiFi, los agentes se detectan automáticamente. Podés verlos en un dashboard tipo radar que te muestra quién está online, quién está ocupado, quién se fue a dormir. Y desde cualquier dispositivo, podés decir "hacé esto en el server" sin pensar en IPs ni conexiones — el mesh se encarga.

**El mesh no es un servicio aparte.** Se carga como un skill en Hermes y todo funciona desde ahí. No hay procesos extra que mantener, no hay servidores que configurar.

---

## Cómo se siente usarlo

### El Radar

Abrís el dashboard y ves un radar oscuro, estilo monitor de submarino. Una línea verde barre la pantalla cada pocos segundos. Cuando pasa sobre un agente, ese punto titila — es el heartbeat. Colores simples:

- 🟢 **Verde:** está online, listo para laburar
- 🟡 **Amarillo:** está ocupado procesando algo
- 🔴 **Rojo:** no responde, se cayó
- ⬤ **Gris:** lo conociste pero nunca más apareció

Pasás el mouse sobre un nodo y ves: nombre del dispositivo, IP, qué está haciendo ahora, hace cuánto está prendido.

### La conexión automática

Ni bien cargás el skill de Hermes Mesh, el agente empieza a anunciarse en la red local. Cuando otro agente con el mismo skill aparece, se detectan al toque. El primero en llegar pregunta:

> *"Se detectó MacBook en la red. ¿Querés conectarlo al mesh?"*

Decís que sí una vez, y de ahí en más se conectan solos cada vez que se ven.

### La delegación natural

Desde cualquier Hermes — estés en la MacBook, en el server, en Windows — podés decir cosas como:

- *"Ejecutame este build en el server que tiene más RAM"*
- *"Correme los tests en Windows que necesito validar compatibilidad"*

No necesitás saber IPs. El mesh sabe quién está conectado y manda la tarea al agente correcto. Si un agente está caído, te avisa.

### La seguridad invisible

Cada agente tiene una identidad. La primera vez que dos agentes se encuentran, te pregunta si querés confiar en el otro. A partir de ahí, se reconocen automáticamente. Para un extraño en la misma WiFi, el mesh es invisible.

---

## Principios de diseño

| Principio | Qué significa |
|---|---|
| **Zero-config** | Llega a la red, se conecta solo. Nada de configurar IPs ni puertos |
| **Auto-discovery** | Los agentes se encuentran sin que hagas nada (mDNS/Zeroconf) |
| **Always visible** | El radar te muestra el estado del mesh de un vistazo |
| **Secure by default** | TOFU (Trust On First Use) — aceptás un peer una vez y después es automático |
| **Graceful degradation** | Si un agente se cae, los demás siguen funcionando |
| **Skill-first** | No es un servicio aparte — se carga como skill en Hermes |

---

## Casos de uso cotidianos

### Escena 1: Desarrollo distribuido

Estás codeando en la MacBook. Necesitás compilar un proyecto pesado que requiere el server. En vez de pushear a GitHub, SSH al server, pullear, compilar, y volver — simplemente le decís al mesh "compilá esto en el server". El mesh manda el código, ejecuta, y te devuelve el resultado todo desde la sesión de Hermes en la MacBook.

### Escena 2: Testing multiplataforma

Escribiste algo en Linux (server). Querés asegurarte de que funciona en Windows. Le decís al mesh "correme los tests en Windows". El agente de Windows lo toma, ejecuta, y te llega el resultado a donde estés.

### Escena 3: Monitoreo pasivo

Tenés el radar abierto en la MacBook mientras hacés otra cosa. Ves que el server está en amarillo — está procesando un scrape largo. La laptop Windows está en verde, sin hacer nada. Sabés que podés tirarle tareas sin molestar a nadie.

### Escena 4: Delegación sin pensar

Estás en el server por SSH, pero necesitás abrir un browser para verificar algo visual. El server no tiene entorno gráfico. Le decís al mesh "abrime esta URL en la MacBook". El mesh sabe que la MacBook tiene display y la manda ahí.

---

## Lo que NO es Hermes Mesh

- **No es un cluster de cómputo distribuido** — no divide una tarea entre varios agentes para sumar poder de procesamiento. Cada tarea va a un agente.
- **No es un reemplazo de SSH** — SSH sigue existiendo para administración manual cuando quieras. El mesh es para delegación entre agentes.
- **No es un VPN** — aunque usa identidad verificada, no crea un túnel de red para todo tu tráfico.
- **No requiere internet** — funciona 100% en red local.

---

## Cómo se usa

1. Instalás el skill de Hermes Mesh en cada agente que quieras conectar
2. El daemon de discovery arranca automáticamente al cargar el skill
3. Los agentes se encuentran solos en la red local
4. La primera vez, aceptás el handshake manualmente
5. De ahí en más, se conectan automáticamente
6. Para delegar, usás comandos como `/mesh delegate server-linux "tarea"`

## Arquitectura (alto nivel)

```
┌──────────────┐     mDNS (Zeroconf)     ┌──────────────┐
│   MacBook    │◄──────────────────────►│    Server     │
│  (dev tasks) │                        │  (heavy work) │
│  Mesh skill  │                        │  Mesh skill   │
└──────┬───────┘                        └──────┬────────┘
       │                                       │
       │              ┌──────────────┐         │
       └─────────────►│ Windows Laptop│◄────────┘
                      │  (light tasks)│
                      │  Mesh skill   │
                      └──────────────┘
```

Cada cuadrado azul es el mismo skill de Hermes Mesh. No hay un servidor central. Todos son pares (peer-to-peer).

## Analogía

**Hermes Mesh es a los agentes lo que una banda de jazz es a los músicos.**

Cada músico (agente) tiene su instrumento y su especialidad. Cuando están juntos en la misma sala (red WiFi), se escuchan, se miran, improvisan. No hay un director de orquesta gritando instrucciones — cada uno sabe lo que hace y se adapta a lo que hacen los demás. El radar es como estar en el público: ves quién está tocando, quién está callado, quién se fue al bar.

Si un músico se va, la música sigue. Si llega uno nuevo, se suma sin ensayar. Es orgánico.

---

*Documento de visión de producto — Mayo 2026 (v2: refactorizado a skill-based architecture)*
