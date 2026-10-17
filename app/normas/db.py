"""SQLite del caso normativa. Una conexión por operación (seguro entre hilos), modo WAL.

Uso:
    from app.normas import db
    with db.connect() as con:
        con.execute("INSERT INTO ...", (...))
    filas = db.query("SELECT * FROM documentos WHERE estado = ?", ("vigente",))
"""
from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Iterator

from app.config import get_settings

ROOT = Path(__file__).resolve().parents[2]

SCHEMA = """
CREATE TABLE IF NOT EXISTS documentos (
    doc_id TEXT PRIMARY KEY,
    nombre_norma TEXT NOT NULL,
    entidad TEXT,
    tipo TEXT,                       -- ley | reglamento | resolucion | circular | politica_interna | manual
    tema TEXT,                       -- uno de TEMAS
    fecha_emision TEXT,              -- AAAA-MM-DD
    fecha_vigencia TEXT,             -- AAAA-MM-DD
    estado TEXT DEFAULT 'vigente',   -- vigente | derogada | reemplazada | por_entrar_en_vigencia
    version TEXT DEFAULT '1',
    reemplaza_a TEXT,                -- doc_id que esta norma reemplaza
    archivo TEXT,
    sha256 TEXT UNIQUE,
    n_chunks INTEGER DEFAULT 0,
    estado_ingesta TEXT DEFAULT 'procesando',  -- procesando | pendiente_confirmacion | indexado | requiere_revision | error
    confirmado INTEGER DEFAULT 0,
    run_id TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS chunks (
    chunk_id TEXT PRIMARY KEY,       -- <doc_id>#art-<n>#c<k>
    doc_id TEXT NOT NULL REFERENCES documentos(doc_id),
    articulo TEXT,
    seccion TEXT,
    pagina INTEGER,
    texto TEXT NOT NULL
);
CREATE VIRTUAL TABLE IF NOT EXISTS chunks_fts USING fts5(chunk_id UNINDEXED, doc_id UNINDEXED, articulo, texto);
CREATE TABLE IF NOT EXISTS discrepancias (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo TEXT NOT NULL,              -- contradice | actualiza | duplica | desactualizada
    severidad TEXT DEFAULT 'media',  -- alta | media | baja
    doc_a TEXT, chunk_a TEXT, cita_a TEXT,
    doc_b TEXT, chunk_b TEXT, cita_b TEXT,
    explicacion TEXT,
    estado_revision TEXT DEFAULT 'pendiente',  -- pendiente | confirmada | descartada
    comentario TEXT,
    run_id TEXT,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS consultas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    canal TEXT, usuario TEXT,
    pregunta TEXT NOT NULL,
    tema TEXT,
    respuesta TEXT,
    confianza TEXT,                  -- alta | media | sin_respaldo
    top_score REAL,
    cubierta INTEGER,
    citas_json TEXT, advertencias_json TEXT,
    run_id TEXT,
    latencia_ms INTEGER,
    created_at TEXT
);
CREATE TABLE IF NOT EXISTS trazas (
    run_id TEXT PRIMARY KEY,
    agente TEXT, canal TEXT, usuario TEXT, modelo TEXT,
    entrada TEXT, salida TEXT,
    pasos_json TEXT,
    latencia_ms INTEGER,
    estado TEXT,
    created_at TEXT, updated_at TEXT
);
CREATE TABLE IF NOT EXISTS brechas (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    consulta_id INTEGER, run_id TEXT,
    tema TEXT, descripcion TEXT,
    created_at TEXT
);
"""

# Columnas agregadas después (KPIs). Filas viejas quedan en NULL = sin dato.
MIGRACIONES = {
    "consultas": [("tipo", "TEXT"), ("n_citas_propuestas", "INTEGER"), ("n_citas_verificadas", "INTEGER"),
                  ("confianza_score", "REAL"), ("advertencia_conflicto", "INTEGER"),
                  ("advertencia_obsoleta", "INTEGER"), ("motivo_sin_cobertura", "TEXT")],
    "trazas": [("started_at", "TEXT"), ("finished_at", "TEXT")],
    "documentos": [("reemplazada_por", "TEXT"), ("estado_actualizado_at", "TEXT")],
}


def _migrar(con: sqlite3.Connection) -> None:
    for tabla, cols in MIGRACIONES.items():
        existentes = {r[1] for r in con.execute(f"PRAGMA table_info({tabla})").fetchall()}
        for nombre, tipo in cols:
            if nombre not in existentes:
                try:
                    con.execute(f"ALTER TABLE {tabla} ADD COLUMN {nombre} {tipo}")
                except sqlite3.OperationalError as e:  # otra conexión la agregó a la vez
                    if "duplicate column" not in str(e).lower():
                        raise

# Lista cerrada de temas: la usan la ingesta (clasificar normas) y las consultas (clasificar preguntas)
TEMAS = [
    "credito_consumo", "credito_hipotecario", "tarjetas", "riesgo_credito", "riesgo_operacional",
    "lavado_activos", "proteccion_consumidor", "transparencia_tasas", "gobierno_corporativo",
    "capital_basilea", "aprobaciones_y_autonomias", "seguridad_informacion", "otros",
]


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def now_ms() -> str:
    return datetime.now().isoformat(timespec="milliseconds")


def db_file() -> Path:
    p = Path(get_settings().db_path)
    return p if p.is_absolute() else ROOT / p


_initialized = False


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    global _initialized
    path = db_file()
    path.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(path, timeout=15)
    con.row_factory = sqlite3.Row
    try:
        if not _initialized:
            con.execute("PRAGMA journal_mode=WAL")
            con.executescript(SCHEMA)
            _migrar(con)
            _initialized = True
        yield con
        con.commit()
    finally:
        con.close()


def query(sql: str, params: tuple | list = ()) -> list[dict[str, Any]]:
    with connect() as con:
        return [dict(r) for r in con.execute(sql, params).fetchall()]


def execute(sql: str, params: tuple | list = ()) -> int:
    """Ejecuta un INSERT/UPDATE/DELETE y devuelve lastrowid."""
    with connect() as con:
        return con.execute(sql, params).lastrowid


def save_trace(run: Any) -> None:
    """Vuelca un Run (app/agents/trace.py) a la tabla trazas. Lo llama RunStore.save."""
    meta = getattr(run, "meta", {}) or {}
    steps = [s if isinstance(s, dict) else s.__dict__ for s in run.steps]
    started = getattr(run, "started_at", None)
    finished = getattr(run, "finished_at", None)
    try:
        if started and finished:
            latency = int((datetime.fromisoformat(finished) - datetime.fromisoformat(started)).total_seconds() * 1000)
        else:
            t0 = datetime.fromisoformat(run.created_at)
            t1 = datetime.fromisoformat(run.updated_at)
            latency = int((t1 - t0).total_seconds() * 1000)
    except ValueError:
        latency = None
    with connect() as con:
        con.execute(
            "INSERT OR REPLACE INTO trazas (run_id, agente, canal, usuario, modelo, entrada, salida, pasos_json,"
            " latencia_ms, estado, created_at, updated_at, started_at, finished_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run.id, meta.get("agente", run.case), meta.get("canal"), meta.get("usuario"),
             meta.get("modelo", get_settings().llm_model), run.input, run.output or run.error,
             json.dumps(steps, ensure_ascii=False, default=str), meta.get("latencia_ms", latency),
             run.status, run.created_at, run.updated_at, started, finished),
        )
