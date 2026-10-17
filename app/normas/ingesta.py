"""Pipeline de ingesta de normas.

    doc_id = ingerir("corpus/SINT-02.txt", metadatos={...})        # metadatos opcionales
    doc_id = ingerir(path, esperar=True)                            # espera la validación (seed)

Pasos: sha256 (dedupe) -> parseo -> metadatos (dados / corpus/metadatos.json / LLM) -> chunking ->
SQLite (documentos, chunks, chunks_fts) -> vector store -> estado vigente/reemplazada/por_entrar ->
agente validador (app/normas/validacion.py).
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import date
from pathlib import Path
from typing import Any

from app.normas import db
from app.normas.chunking import chunkear
from app.normas.parsing import parsear
from app.normas.vector import fecha_int, get_store

log = logging.getLogger("ingesta")

CORPUS_META = db.ROOT / "corpus" / "metadatos.json"
CAMPOS = ["doc_id", "nombre_norma", "entidad", "tipo", "tema", "fecha_emision", "fecha_vigencia",
          "version", "reemplaza_a"]
TIPOS = ["ley", "reglamento", "resolucion", "circular", "politica_interna", "manual"]


def sha256_de(path: str | Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def metadatos_corpus(nombre_archivo: str) -> dict[str, Any] | None:
    """Metadatos conocidos de los documentos de demo (carga determinista)."""
    try:
        data = json.loads(CORPUS_META.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None
    m = data.get(Path(nombre_archivo).name)
    return dict(m) if m else None


def doc_por_sha(sha: str) -> dict[str, Any] | None:
    rows = db.query("SELECT * FROM documentos WHERE sha256 = ?", (sha,))
    return rows[0] if rows else None


# ---------------------------------------------------------------------------- metadatos con LLM
def _json_tolerante(texto: str) -> dict[str, Any]:
    texto = re.sub(r"^```(json)?|```$", "", texto.strip(), flags=re.M).strip()
    m = re.search(r"\{.*\}", texto, re.S)
    if not m:
        return {}
    try:
        return json.loads(m.group(0))
    except ValueError:
        try:
            return json.loads(re.sub(r",\s*}", "}", m.group(0).replace("'", '"')))
        except ValueError:
            return {}


def _fecha(v: Any) -> str | None:
    if not v:
        return None
    m = re.search(r"(\d{4})-(\d{1,2})-(\d{1,2})", str(v))
    return f"{m.group(1)}-{int(m.group(2)):02d}-{int(m.group(3)):02d}" if m else None


def extraer_metadatos_llm(texto: str) -> dict[str, Any]:
    from app.llm_client import get_llm

    existentes = db.query("SELECT doc_id, nombre_norma, version, estado FROM documentos")
    prompt = (
        "Extrae los metadatos de esta norma/política bancaria. Responde SOLO un objeto JSON con las claves: "
        "nombre_norma, entidad, tipo, tema, fecha_emision (AAAA-MM-DD), fecha_vigencia (AAAA-MM-DD), "
        "version (texto, ej. \"1\"), reemplaza_a.\n"
        f"- tipo debe ser uno de: {', '.join(TIPOS)}\n"
        f"- tema debe ser uno de: {', '.join(db.TEMAS)}\n"
        "- reemplaza_a: el doc_id de la lista de documentos existentes que esta norma reemplaza "
        "(solo si el texto lo dice explícitamente), si no null.\n"
        "- Si un dato no aparece, usa null.\n\n"
        f"Documentos existentes: {json.dumps(existentes, ensure_ascii=False)}\n\n"
        f"Texto (inicio):\n{texto[:4000]}"
    )
    try:
        resp = get_llm().chat([{"role": "user", "content": prompt}], temperature=0)
        return _json_tolerante(resp.content)
    except Exception as e:
        log.exception("Extracción de metadatos con LLM falló")
        return {"_error": str(e)}


def completar_metadatos(meta: dict[str, Any] | None, texto: str, sha: str) -> dict[str, Any]:
    meta = {k: v for k, v in (meta or {}).items() if v not in ("", None) or k == "reemplaza_a"}
    faltan = [c for c in CAMPOS if c not in meta and c not in ("doc_id", "reemplaza_a")]
    if faltan:
        llm = extraer_metadatos_llm(texto)
        for c in CAMPOS:
            if c not in meta and llm.get(c) not in (None, ""):
                meta[c] = llm[c]
    meta.setdefault("doc_id", f"DOC-{sha[:8].upper()}")
    meta.setdefault("nombre_norma", meta["doc_id"])
    if meta.get("tema") not in db.TEMAS:
        meta["tema"] = "otros"
    if meta.get("tipo") not in TIPOS:
        meta["tipo"] = meta.get("tipo") or "politica_interna"
    meta["fecha_emision"] = _fecha(meta.get("fecha_emision"))
    meta["fecha_vigencia"] = _fecha(meta.get("fecha_vigencia")) or meta["fecha_emision"]
    meta["version"] = str(meta.get("version") or "1")
    ra = meta.get("reemplaza_a")
    meta["reemplaza_a"] = ra if ra and db.query("SELECT 1 FROM documentos WHERE doc_id = ?", (ra,)) else (ra or None)
    return meta


# ---------------------------------------------------------------------------- vector store
def records_de(doc_id: str) -> list[dict[str, Any]]:
    """Registros del vector store reconstruidos desde SQLite (texto con prefijo + metadatos)."""
    docs = db.query("SELECT * FROM documentos WHERE doc_id = ?", (doc_id,))
    if not docs:
        return []
    d = docs[0]
    out = []
    for c in db.query("SELECT * FROM chunks WHERE doc_id = ? ORDER BY rowid", (doc_id,)):
        etiqueta = f"Art. {c['articulo']}" if str(c["articulo"]).isdigit() else c["articulo"]
        out.append({
            "id": c["chunk_id"],
            "text": f"[{d['nombre_norma']} v{d['version']} · {etiqueta}] {c['texto']}",
            "doc_id": doc_id, "nombre_norma": d["nombre_norma"], "entidad": d["entidad"],
            "tipo": d["tipo"], "tema": d["tema"], "articulo": str(c["articulo"]),
            "pagina": c["pagina"], "fecha_emision": fecha_int(d["fecha_emision"]),
            "fecha_vigencia": fecha_int(d["fecha_vigencia"]), "estado": d["estado"],
            "version": d["version"], "reemplaza_a": d["reemplaza_a"],
        })
    return out


def reindexar(doc_id: str) -> int:
    recs = records_de(doc_id)
    return get_store().upsert(recs) if recs else 0


def _estado_inicial(meta: dict[str, Any]) -> str:
    if db.query("SELECT 1 FROM documentos WHERE reemplaza_a = ?", (meta["doc_id"],)):
        return "reemplazada"  # se cargó una versión posterior antes que esta
    fv = meta.get("fecha_vigencia")
    if fv and fv > date.today().isoformat():
        return "por_entrar_en_vigencia"
    return "vigente"


# ---------------------------------------------------------------------------- pipeline
def ingerir(path: str | Path, metadatos: dict[str, Any] | None = None, validar: bool = True,
            esperar: bool = False, usuario: str = "sistema", canal: str = "web") -> str:
    path = Path(path)
    sha = sha256_de(path)
    previo = doc_por_sha(sha)
    if previo:
        log.info("Documento duplicado (sha256): %s ya existe como %s", path.name, previo["doc_id"])
        return previo["doc_id"]

    paginas, basura, motivo = parsear(path)
    texto = "\n".join(t for _, t in paginas)
    if metadatos is None:
        metadatos = metadatos_corpus(path.name)
    meta = completar_metadatos(metadatos, texto, sha)
    doc_id = meta["doc_id"]
    if db.query("SELECT 1 FROM documentos WHERE doc_id = ?", (doc_id,)):
        doc_id = meta["doc_id"] = f"{doc_id}-{sha[:6].upper()}"  # mismo id, contenido distinto

    estado = _estado_inicial(meta)
    chunks = chunkear(paginas, meta) if texto.strip() else []
    with db.connect() as con:
        con.execute(
            "INSERT INTO documentos (doc_id, nombre_norma, entidad, tipo, tema, fecha_emision, fecha_vigencia,"
            " estado, version, reemplaza_a, archivo, sha256, n_chunks, estado_ingesta, confirmado, created_at)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (doc_id, meta["nombre_norma"], meta.get("entidad"), meta.get("tipo"), meta.get("tema"),
             meta.get("fecha_emision"), meta.get("fecha_vigencia"), estado, meta["version"],
             meta.get("reemplaza_a"), str(path), sha, len(chunks), "procesando", 1 if metadatos else 0, db.now()),
        )
        for c in chunks:
            con.execute("INSERT INTO chunks (chunk_id, doc_id, articulo, seccion, pagina, texto) VALUES (?,?,?,?,?,?)",
                        (c["chunk_id"], doc_id, c["articulo"], c["seccion"], c["pagina"], c["texto"]))
            con.execute("INSERT INTO chunks_fts (chunk_id, doc_id, articulo, texto) VALUES (?,?,?,?)",
                        (c["chunk_id"], doc_id, c["articulo"], c["texto"]))

    try:
        reindexar(doc_id)
        ra = meta.get("reemplaza_a")
        if ra and db.query("SELECT 1 FROM documentos WHERE doc_id = ?", (ra,)):
            db.execute("UPDATE documentos SET estado = 'reemplazada' WHERE doc_id = ?", (ra,))
            reindexar(ra)
            log.info("%s reemplaza a %s: marcado como reemplazada", doc_id, ra)
    except Exception as e:
        log.exception("Error indexando %s", doc_id)
        db.execute("UPDATE documentos SET estado_ingesta = 'error' WHERE doc_id = ?", (doc_id,))
        raise RuntimeError(f"Error indexando {doc_id}: {e}") from e

    estado_ingesta = "requiere_revision" if basura or not chunks else "indexado"
    db.execute("UPDATE documentos SET estado_ingesta = ? WHERE doc_id = ?", (estado_ingesta, doc_id))
    if basura:
        log.warning("%s requiere revisión: %s", doc_id, motivo)
    log.info("Ingerido %s (%d chunks, estado=%s, ingesta=%s)", doc_id, len(chunks), estado, estado_ingesta)

    if validar and chunks and not basura:
        from app.normas.validacion import validar_documento
        validar_documento(doc_id, usuario=usuario, canal=canal, background=not esperar)
    return doc_id
