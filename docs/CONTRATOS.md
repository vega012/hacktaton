# Contratos entre módulos (caso B2 normativa)

## Módulos compartidos (no cambiar la firma sin avisar)
- `app/normas/db.py`: `db.query(sql, params)`, `db.execute(sql, params)`, `db.connect()`, `db.TEMAS`, `db.now()`. Esquema en `SCHEMA`.
- `app/normas/vector.py`: `get_store().upsert(records)`, `.search(text, top_k, filter, rerank_top_n) -> [Hit]`, `fecha_int("2025-03-01") -> 20250301`.
- `app/agents/*`: `Agent`, `Flow`, `engine`, `@tool`, `Run.meta = {"agente","canal","usuario"}` (se guarda en la tabla `trazas`).
- `app/llm_client.py`: `get_llm().chat(messages, tools=None, temperature=0)`.

## Registro en Pinecone
`id = "<doc_id>#art-<n>#c<k>"`, `text` = texto con prefijo `[<nombre_norma> v<version> · Art. <n>]`.
Metadatos: `doc_id, nombre_norma, entidad, tipo, tema, articulo, pagina, fecha_emision (int), fecha_vigencia (int), estado, version, reemplaza_a`.

## Frente A — Ingesta y validación (`app/normas/api_documentos.py`)
| Ruta | Entrada | Salida |
|---|---|---|
| `POST /api/documentos` | multipart `archivo` | `{doc_id, run_id, estado_ingesta}` |
| `GET /api/documentos` | — | `[{doc_id, nombre_norma, entidad, tipo, tema, fecha_emision, fecha_vigencia, estado, version, reemplaza_a, n_chunks, estado_ingesta}]` |
| `GET /api/documentos/{doc_id}` | — | documento + `chunks` + `discrepancias` |
| `GET /api/discrepancias?doc_id=` | — | `[{id, tipo, severidad, doc_a, cita_a, doc_b, cita_b, explicacion, estado_revision, created_at}]` |
| `POST /api/discrepancias/{id}/revisar` | `{decision: "confirmada"|"descartada", comentario}` | `{ok}` |

## Frente B — Consultas, trazas y dashboard (`app/normas/api_consultas.py`)
| Ruta | Entrada | Salida |
|---|---|---|
| `POST /api/consultas` | `{pregunta, canal, usuario}` | `{respuesta, confianza: alta|media|sin_respaldo, cubierta, citas:[{doc_id, nombre_norma, articulo, version, estado, texto}], advertencias:[str], tema, top_score, run_id, latencia_ms}` |
| `GET /api/trazas?agente=&limit=` | — | `[{run_id, agente, canal, usuario, modelo, entrada, salida, latencia_ms, estado, created_at}]` |
| `GET /api/trazas/{run_id}` | — | fila completa con `pasos` (lista de Step) |
| `GET /api/dashboard` | — | `{top_normas:[{doc_id, nombre_norma, n}], sin_cobertura:[{tema, n, ejemplos}], discrepancias:{total, por_tipo, recientes}, uso:{consultas_total, consultas_hoy, pct_cubiertas, latencia_p50_ms, documentos, chunks}}` |

Canales (clientes delgados, sin lógica): bot de Telegram y Streamlit llaman a estos endpoints vía `API_BASE_URL`.

## Frente C — Chat de casos (`app/normas/api_chat.py`, `app/normas/casos.py`, `app/static/chat.html` en `/chat`)
Interfaz de chat separada (reemplaza a Telegram). El usuario describe o sube (PDF/DOCX/TXT) un caso concreto y el
agente lo evalúa contra las normas cargadas; también responde consultas simples y preguntas de seguimiento.

| Ruta | Entrada | Salida |
|---|---|---|
| `POST /api/chat` | multipart: `session_id`, `mensaje`, `archivo?` | ver abajo |
| `GET /api/chat/ejemplos` | — | `[{id, titulo, texto}]` casos de ejemplo para la demo |
| `GET /api/chat/{session_id}` | — | `[{rol: "usuario"|"agente", contenido, tipo, payload, run_id, created_at}]` |

Respuesta de `POST /api/chat`:
```json
{
  "session_id": "s1", "run_id": "r_1", "tipo": "consulta | caso", "latencia_ms": 9000,
  "respuesta": "texto breve para la burbuja del chat",
  "confianza": "alta | media | sin_respaldo",
  "citas": [{"doc_id", "nombre_norma", "articulo", "version", "estado", "texto"}],
  "advertencias": ["..."],
  "dictamen": null | {
    "resumen_caso": "...",
    "hechos": [{"dato": "Ingreso neto mensual", "valor": "S/ 6,000"}],
    "evaluaciones": [{"regla", "doc_id", "nombre_norma", "articulo", "version", "estado", "cita",
                      "resultado": "cumple | no_cumple | indeterminado", "explicacion"}],
    "calculos": [{"descripcion", "expresion", "resultado"}],
    "conflictos": ["..."], "vacios": ["aspectos del caso sin norma que los regule"],
    "conclusion": "procede | procede_con_observaciones | no_procede | requiere_escalamiento",
    "acciones": ["..."]
  }
}
```

## KPIs (`app/normas/kpis.py`, `app/normas/api_kpis.py`, sección KPIs en `ui/streamlit_app.py`)
Regla: todo sale de datos registrados por los agentes. `valor: null` = **sin datos** (la UI muestra "sin datos").
Cada porcentaje trae `num` y `den` para poder explicar de dónde sale.

`GET /api/kpis?desde=&hasta=&umbral=&tiempo_manual_min=15&granularidad=hora`
(`desde`/`hasta`: fecha `AAAA-MM-DD` o fecha-hora ISO; `granularidad`: `10min | hora | dia`; `umbral` por defecto U2 del backend)
```json
{
  "rango": {"desde": "...", "hasta": "..."}, "backend": "pinecone | local", "umbral": 0.10, "generado_at": "...",
  "calidad": {
    "total_consultas": 40, "por_tipo": {"consulta": 32, "caso": 8},
    "con_cita":           {"valor": 0.85, "num": 34, "den": 40},
    "sin_cobertura":      {"valor": 0.15, "num": 6, "den": 40, "no_encontro": 4, "score_bajo": 2},
    "con_advertencia":    {"valor": 0.40, "num": 16, "den": 40, "conflicto": 9, "obsoleta": 11},
    "confianza_promedio": {"valor": 0.71, "n": 34, "distribucion": {"alta": 20, "media": 14, "sin_respaldo": 6}}
  },
  "prevencion": {
    "discrepancias": {"total": 3, "por_severidad": {"alta": 1, "media": 2}, "por_tipo": {"contradice": 1, "actualiza": 2}},
    "normas_obsoletas": {"total": 1, "lista": [{"doc_id", "nombre_norma", "estado", "reemplazada_por"}]},
    "afectados_por_norma": [{"doc_id", "nombre_norma", "n": 2, "afectados": ["SINT-02", "SINT-01"]}]
  },
  "eficiencia": {
    "tiempo_respuesta_s": {"promedio": 12.3, "mediana": 9.8, "n": 40,
                           "por_agente": {"consultas": {"promedio", "mediana", "n"}, "analista_casos": {...}, "validador": {...}}},
    "tiempo_ahorrado": {"estimado": true, "tiempo_manual_min": 15, "consultas": 40, "horas": 9.9,
                        "supuesto": "consultas × (tiempo manual de referencia − tiempo promedio del agente)"}
  },
  "trazabilidad": {
    "trazas_completas": {"valor": 1.0, "num": 44, "den": 44, "incompletas": [{"run_id", "agente", "faltan": ["fragmentos"]}]},
    "top_normas": [{"doc_id", "nombre_norma", "n"}],
    "brechas": [{"tema", "n", "ejemplos": ["..."]}]
  },
  "tendencia": {
    "granularidad": "hora",
    "consultas": [{"t": "2026-10-17T13:00", "n": 12, "sin_cobertura": 2}],
    "brechas_por_tema": [{"tema", "n"}]
  }
}
```
