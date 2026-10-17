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
