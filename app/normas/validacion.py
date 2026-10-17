"""Agente validador: compara un documento recién ingerido con el resto del corpus.

- Python preselecciona los chunks con cifras (%, S/, números) — máximo 8 — y se los pasa en la tarea.
- El agente usa val_buscar_candidatos (top 5 de OTROS documentos) y val_registrar_discrepancia,
  que verifica que las citas sean textuales antes de guardar (evita alucinaciones).
"""
from __future__ import annotations

import logging
import re
from typing import Any

from app.agents.agent import Agent
from app.agents.engine import engine
from app.agents.flow import Flow
from app.agents.tools import tool
from app.agents.trace import Run
from app.normas import db
from app.normas.vector import get_store

log = logging.getLogger("validacion")

MAX_CHUNKS = 8
TIPOS = ["contradice", "actualiza", "duplica", "desactualizada"]
SEVERIDADES = ["alta", "media", "baja"]
_CABECERA = re.compile(r"^\s*(Art[íi]culo|Art\.)\s+\d+\s*[.:°º-]*", re.I)


def _norm(t: str) -> str:
    t = t.replace("“", '"').replace("”", '"').replace("’", "'").replace(" ", " ")
    return " ".join(t.split()).strip(" .\"'").lower()


def _chunk(chunk_id: str) -> dict[str, Any] | None:
    rows = db.query("SELECT c.*, d.nombre_norma, d.version, d.estado FROM chunks c "
                    "JOIN documentos d ON d.doc_id = c.doc_id WHERE c.chunk_id = ?", (chunk_id,))
    return rows[0] if rows else None


# ---------------------------------------------------------------------------- tools
@tool(name="val_buscar_candidatos",
      description="Busca los 5 fragmentos más parecidos de OTROS documentos al fragmento indicado.",
      params={"chunk_id": "ID del fragmento del documento nuevo (ej. SINT-03#art-12#c0)"})
def val_buscar_candidatos(chunk_id: str) -> dict:
    c = _chunk(chunk_id)
    if not c:
        return {"error": f"No existe el fragmento {chunk_id}"}
    hits = get_store().search(c["texto"], top_k=20, filter={"doc_id": {"$ne": c["doc_id"]}}, rerank_top_n=5)
    out = []
    for h in hits[:5]:
        cc = _chunk(h.id)
        md = h.metadata
        out.append({"chunk_id": h.id, "score": round(h.best_score, 3), "doc_id": md.get("doc_id"),
                    "nombre_norma": md.get("nombre_norma"), "version": md.get("version"),
                    "estado": md.get("estado"), "articulo": md.get("articulo"),
                    "texto": cc["texto"] if cc else h.text})
    return {"chunk_id": chunk_id, "candidatos": out}


@tool(name="val_registrar_discrepancia",
      description=("Registra una discrepancia entre un fragmento del documento nuevo (a) y otro existente (b). "
                   "Las citas deben ser copias TEXTUALES de los fragmentos."),
      params={"tipo": f"Uno de: {', '.join(TIPOS)}",
              "severidad": "alta | media | baja",
              "chunk_a": "chunk_id del documento nuevo",
              "cita_a": "Frase textual de chunk_a con la cifra en conflicto",
              "chunk_b": "chunk_id del otro documento",
              "cita_b": "Frase textual de chunk_b con la cifra en conflicto",
              "explicacion": "Explicación breve de la discrepancia"})
def val_registrar_discrepancia(tipo: str, severidad: str, chunk_a: str, cita_a: str, chunk_b: str,
                               cita_b: str, explicacion: str) -> dict:
    if tipo not in TIPOS:
        return {"error": f"tipo inválido; usa uno de {TIPOS}"}
    if severidad not in SEVERIDADES:
        severidad = "media"
    a, b = _chunk(chunk_a), _chunk(chunk_b)
    if not a or not b:
        return {"error": f"No existe el fragmento {chunk_a if not a else chunk_b}"}
    if a["doc_id"] == b["doc_id"]:
        return {"error": "Los fragmentos deben ser de documentos distintos"}
    if not cita_a.strip() or _norm(cita_a) not in _norm(a["texto"]):
        return {"error": f"cita_a no aparece textualmente en {chunk_a}. Copia una frase exacta de: {a['texto']}"}
    if not cita_b.strip() or _norm(cita_b) not in _norm(b["texto"]):
        return {"error": f"cita_b no aparece textualmente en {chunk_b}. Copia una frase exacta de: {b['texto']}"}
    if db.query("SELECT 1 FROM discrepancias WHERE chunk_a = ? AND chunk_b = ?", (chunk_a, chunk_b)):
        return {"ok": True, "nota": "Esa discrepancia ya estaba registrada"}
    run = db.query("SELECT run_id FROM documentos WHERE doc_id = ?", (a["doc_id"],))
    new_id = db.execute(
        "INSERT INTO discrepancias (tipo, severidad, doc_a, chunk_a, cita_a, doc_b, chunk_b, cita_b, explicacion,"
        " run_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        (tipo, severidad, a["doc_id"], chunk_a, cita_a.strip(), b["doc_id"], chunk_b, cita_b.strip(),
         explicacion.strip(), run[0]["run_id"] if run else None, db.now()),
    )
    return {"ok": True, "id": new_id}


# ---------------------------------------------------------------------------- agente
validador = Agent(
    name="validador",
    role=(
        "Eres el agente validador de normativa de un banco. Revisas los fragmentos de un documento NUEVO "
        "y los comparas con el resto del corpus para detectar conflictos.\n"
        "Procedimiento: para CADA fragmento listado llama a val_buscar_candidatos (puedes llamar varias a la vez). "
        "Compara solo candidatos que regulen LA MISMA regla (mismo sujeto y misma materia: p. ej. límite de "
        "aprobación del gerente de agencia, porcentaje de endeudamiento, puntaje mínimo, plazos).\n"
        "Registra con val_registrar_discrepancia:\n"
        "- 'contradice' (severidad alta): el candidato es de un documento VIGENTE y fija una cifra/monto/límite/plazo "
        "distinto para la misma regla.\n"
        "- 'actualiza' (severidad media): el documento nuevo es una versión posterior y el candidato es de la versión "
        "'reemplazada' con una cifra distinta para la misma regla.\n"
        "NO registres textos idénticos, ni reglas distintas que solo se parecen, ni diferencias entre un documento "
        "nuevo y una versión reemplazada que no sea la que él reemplaza. cita_a y cita_b deben ser copias textuales "
        "de una frase del fragmento (incluyendo la cifra). Si la herramienta devuelve error, corrige la cita.\n"
        "Al final responde con un resumen breve: cuántas discrepancias registraste y cuáles."
    ),
    tools=["val_buscar_candidatos", "val_registrar_discrepancia"],
    max_iterations=20,
    temperature=0,
)

FLOW = Flow(agents=[validador])


def chunks_con_cifras(doc_id: str) -> list[dict[str, Any]]:
    rows = db.query("SELECT chunk_id, articulo, texto FROM chunks WHERE doc_id = ? ORDER BY rowid", (doc_id,))
    fuertes, debiles = [], []
    for r in rows:
        if r["articulo"] == "preámbulo":
            continue
        cuerpo = _CABECERA.sub("", r["texto"], count=1)
        if re.search(r"%|S/", cuerpo):
            fuertes.append(r)
        elif re.search(r"\d", cuerpo):
            debiles.append(r)
    return (fuertes + debiles)[:MAX_CHUNKS]


def validar_documento(doc_id: str, usuario: str = "sistema", canal: str = "web",
                      background: bool = True) -> Run | None:
    doc = db.query("SELECT * FROM documentos WHERE doc_id = ?", (doc_id,))
    if not doc:
        raise KeyError(doc_id)
    d = doc[0]
    chunks = chunks_con_cifras(doc_id)
    if not chunks:
        log.info("%s: sin fragmentos con cifras, no se valida", doc_id)
        return None
    lista = "\n".join(f"- {c['chunk_id']}: {' '.join(c['texto'].split())}" for c in chunks)
    tarea = (
        f"Documento nuevo: {doc_id} — {d['nombre_norma']} v{d['version']} (estado {d['estado']}, "
        f"vigente desde {d['fecha_vigencia']}"
        + (f", reemplaza a {d['reemplaza_a']}" if d["reemplaza_a"] else "") + ").\n"
        f"Fragmentos a revisar ({len(chunks)}):\n{lista}\n\n"
        "Busca candidatos para cada uno y registra las contradicciones o actualizaciones que encuentres."
    )
    run = engine.start(FLOW, tarea, case="validacion", background=background)
    run.meta = {"agente": "validador", "canal": canal, "usuario": usuario}
    db.execute("UPDATE documentos SET run_id = ? WHERE doc_id = ?", (run.id, doc_id))
    if not background:  # en modo síncrono el run ya terminó: completar run_id y meta
        db.execute("UPDATE discrepancias SET run_id = ? WHERE doc_a = ? AND run_id IS NULL", (run.id, doc_id))
        engine.store.save(run)
    return run
