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

---

## Cómo se siente usarlo

### El Radar

Abrís el dashboard y ves un radar oscuro, estilo monitor de submarino. Una línea verde barre la pantalla cada pocos segundos. Cuando pasa sobre un agente, ese punto titila — es el heartbeat. Colores simples:

- 🟢 **Verde:** está online, listo para laburar
- 🟡 **Amarillo:** está ocupado procesando algo
- 🔴 **Rojo:** no responde, se cayó
- ⬤ **Gris:** lo conociste pero nunca más apareció

Pasás el mouse sobre un nodo y ves: nombre del dispositivo, IP, qué está haciendo ahora, hace cuánto está prendido.

### La delegación natural

Desde cualquier Hermes — estés en la MacBook, en el server, en Windows — podés decir cosas como:

- *"Ejecutame este build en el server que tiene más RAM"*
- *"Abrí el browser en la MacBook y buscame esto"*
- *"Correme los tests en Windows que necesito validar compatibilidad"*

No necesitás saber IPs. El mesh sabe quién puede hacer qué y lo manda al mejor candidato. Si un agente está caído, busca otro automáticamente.

### La seguridad invisible

Cada agente tiene su identidad criptográfica. Cuando dos agentes se encuentran en la red, se reconocen como "de los nuestros". Lo que se dicen entre ellos va encriptado. Para un extraño en la misma WiFi, es ruido. Para tus agentes, es conversación privada.

---

## Principios de diseño

| Principio | Qué significa |
|---|---|
| **Zero-config** | Llega a la red, se conecta solo. Nada de configurar IPs ni puertos |
| **Auto-discovery** | Los agentes se encuentran sin que hagas nada |
| **Always visible** | El radar te muestra el estado del mesh de un vistazo |
| **Secure by default** | Toda comunicación va encriptada con identidad verificada |
| **Graceful degradation** | Si un agente se cae, los demás siguen funcionando y se acomodan |

---

## Casos de uso cotidianos

### Escena 1: Desarrollo distribuido

Estás codeando en la MacBook. Necesitás compilar un proyecto pesado que requiere el server. En vez de pushear a GitHub, SSH al server, pullear, compilar, y volver — simplemente le decís al mesh "compilá esto en el server". El mesh manda el código, ejecuta, y te devuelve el resultado.

### Escena 2: Testing multiplataforma

Escribiste algo en Linux (server). Querés asegurarte de que funciona en Windows y macOS. Le decís al mesh "correme los tests en los tres dispositivos". Cada uno ejecuta lo suyo y te llega el reporte consolidado.

### Escena 3: Monitoreo pasivo

Tenés el radar abierto en la MacBook mientras hacés otra cosa. Ves que el server está en amarillo — está procesando un scrape largo. La laptop Windows está en verde, sin hacer nada. Sabés que podés tirarle tareas sin molestar a nadie.

### Escena 4: Delegación inteligente

Estás en el server por SSH, pero necesitás abrir un browser para verificar algo visual. El server no tiene entorno gráfico. Le decís al mesh "abrime esta URL en la MacBook". El mesh sabe que la MacBook tiene display y la manda ahí.

---

## Lo que NO es Hermes Mesh

- **No es un cluster de cómputo distribuido** — no divide una tarea entre varios agentes para sumar poder de procesamiento (eso sería tipo Nexo/BONIC). Cada tarea va a un agente.
- **No es un reemplazo de SSH** — SSH sigue existiendo para administración manual cuando quieras. El mesh es para delegación entre agentes.
- **No es un VPN** — aunque usa encriptación, el mesh no crea un túnel de red para todo tu tráfico. Solo protege la comunicación entre agentes Hermes.
- **No requiere internet** — funciona 100% en red local. Si los agentes están en redes distintas, se puede extender con Tailscale/WireGuard, pero no es requisito.

---

## Analogía

**Hermes Mesh es a los agentes lo que una banda de jazz es a los músicos.**

Cada músico (agente) tiene su instrumento y su especialidad. Cuando están juntos en la misma sala (red WiFi), se escuchan, se miran, improvisan. No hay un director de orquesta gritando instrucciones — cada uno sabe lo que hace y se adapta a lo que hacen los demás. El radar es como estar en el público: ves quién está tocando, quién está callado, quién se fue al bar.

Si un músico se va, la música sigue. Si llega uno nuevo, se suma sin ensayar. Es orgánico.

---

## Próximos pasos

1. **Definir arquitectura técnica** — Spec Master Skill desde la MacBook
2. **Spike del radar** — dashboard visual con p5.js para validar el concepto
3. **Discovery + heartbeat** — el núcleo del mesh
4. **Seguridad** — identidad, encriptación, mTLS
5. **Delegación** — task routing entre agentes

---

*Documento de visión de producto — Mayo 2026*
*Para arquitectura técnica, correr Spec Master Skill sobre este documento.*
