# Pitch — [Nombre del proyecto]

> Duración sugerida: 3–5 min. Sector: **[Banca / Minería / Manufactura]**. Equipo: [nombres].

## 1. Problema (30–45 s)

- **Quién lo sufre:** [rol / área — ej. analistas de crédito, supervisores de mantenimiento, jefes de calidad]
- **Qué pasa hoy:** [proceso manual, lento, con errores — describir en una frase]
- **Cuánto cuesta:** [dato concreto: horas por caso, casos por día, costo de un error, multas, paradas]
- **Por qué ahora:** [volumen creciente, regulación, falta de personal, riesgo de seguridad]

> Frase gancho: "[Hoy, un ___ tarda ___ en ___, y un error cuesta ___]."

## 2. Solución (30–45 s)

- [Nombre] es un equipo de agentes de IA que **[verbo + resultado]** de punta a punta.
- Consulta los datos, aplica las reglas del negocio, ejecuta las acciones y **pide aprobación humana** en lo crítico.
- Cada decisión queda **trazada y explicada**: auditable, no una caja negra.

## 3. Agentes de IA (45 s)

| Agente | Rol | Herramientas | Decide / ejecuta |
|---|---|---|---|
| [agente 1] | [ej. analiza y diagnostica] | [tools de consulta] | Traspasa al agente 2 si hay acción |
| [agente 2] | [ej. ejecuta y reporta] | [tools de acción] | Acciones sensibles → aprobación humana |

- **Guardrails:** [ej. monto máximo X, acciones prohibidas, validación de política antes de ejecutar].
- **Humano en el loop:** [qué acciones requieren aprobación y quién aprueba].
- **Arquitectura abierta:** LLM intercambiable (un solo módulo) y transporte entre agentes listo para protocolos como NANDA.

## 4. Demo (60–90 s) — en vivo

URL: **[http://IP o https://host]**

1. Lanzar el caso: "[texto del caso]".
2. Mostrar en vivo: razonamiento → consulta de datos → traspaso entre agentes.
3. La acción sensible queda **pendiente**: aprobar (o rechazar con comentario) en pantalla.
4. Mostrar el resultado final y la traza completa.

> Plan B si falla la red: [video / capturas / correr local con `docker compose up`].

## 5. Impacto (45 s)

| Métrica | Hoy (manual) | Con agentes | Mejora |
|---|---|---|---|
| Tiempo por caso | [ej. 45 min] | [ej. 3 min] | [ej. -93%] |
| Casos por persona al día | [ ] | [ ] | [ ] |
| Errores / incumplimientos de política | [ ] | [ ] (guardrails) | [ ] |
| Costo por caso | [ ] | [ ] (costo LLM ≈ centavos) | [ ] |
| Trazabilidad / auditoría | [parcial / manual] | 100% de los pasos | — |

Métricas sugeridas según sector:
- **Banca:** tiempo de respuesta de una solicitud, % de solicitudes evaluadas con política completa, fraudes detectados / pérdidas evitadas.
- **Minería:** horas de parada no planificada evitadas, tiempo de detección de una anomalía, incidentes de seguridad prevenidos.
- **Manufactura:** unidades defectuosas que no llegan al cliente, tiempo de replanificación, % de scrap / reprocesos.

> Supuestos del cálculo: [volumen anual, costo hora, costo de un error]. Escalable a [N] plantas / sucursales.

## 6. Código (15 s)

- Repositorio: **[URL]**
- Stack: Python, FastAPI, DeepSeek (API compatible con OpenAI), Docker Compose, Caddy.
- Próximos pasos: [integrar sistemas reales, más agentes, conexión NANDA, métricas en producción].
