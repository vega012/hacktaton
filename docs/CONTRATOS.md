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
