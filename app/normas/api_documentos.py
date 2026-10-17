"""Endpoints de ingesta y validación (frente A). Contrato en docs/CONTRATOS.md."""
from __future__ import annotations

import asyncio
import hashlib
import logging
import re
import threading
import time
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.normas import db
from app.normas.ingesta import doc_por_sha, ingerir, metadatos_corpus

log = logging.getLogger("api_documentos")
router = APIRouter(tags=["documentos"])

UPLOADS = db.ROOT / "data" / "uploads"
COLS_DOC = ("doc_id, nombre_norma, entidad, tipo, tema, fecha_emision, fecha_vigencia, estado, version, "
            "reemplaza_a, n_chunks, estado_ingesta, run_id, created_at")
COLS_DISC = ("id, tipo, severidad, doc_a, chunk_a, cita_a, doc_b, chunk_b, cita_b, explicacion, "
             "estado_revision, comentario, run_id, created_at")


@router.post("/documentos", status_code=202)
async def subir_documento(archivo: UploadFile = File(...)) -> JSONResponse:
    nombre = Path(archivo.filename or "documento.txt").name
    if Path(nombre).suffix.lower() not in (".pdf", ".docx", ".txt"):
        raise HTTPException(400, "Formato no soportado: usa PDF, DOCX o TXT")
    UPLOADS.mkdir(parents=True, exist_ok=True)
    nombre = re.sub(r"[^\w.\-]", "_", nombre)
    destino = UPLOADS / nombre
    if destino.exists():
        destino = UPLOADS / f"{int(time.time())}_{nombre}"
    destino.write_bytes(await archivo.read())

    sha = hashlib.sha256(destino.read_bytes()).hexdigest()
    previo = doc_por_sha(sha)
    if previo:
        return JSONResponse({"doc_id": previo["doc_id"], "run_id": previo["run_id"],
                             "estado_ingesta": previo["estado_ingesta"], "duplicado": True}, status_code=200)

    # doc_id conocido de antemano (corpus de demo o derivado del hash) para poder responder ya
    meta = metadatos_corpus(nombre) or {"doc_id": f"DOC-{sha[:8].upper()}"}
    doc_id = meta["doc_id"]
    error: list[str] = []

    def trabajo() -> None:
        try:
            ingerir(destino, metadatos=meta, usuario="web", canal="web")
        except Exception as e:
            log.exception("Ingesta de %s falló", nombre)
            error.append(str(e))

    hilo = threading.Thread(target=trabajo, name=f"ingesta-{doc_id}", daemon=True)
    hilo.start()
    # Espera breve a que el documento quede indexado y arranque el validador (para devolver run_id)
    run_id, estado = None, "procesando"
    for _ in range(100):
        rows = db.query("SELECT run_id, estado_ingesta FROM documentos WHERE doc_id = ?", (doc_id,))
        if rows:
            run_id, estado = rows[0]["run_id"], rows[0]["estado_ingesta"]
            if run_id or estado in ("requiere_revision", "error"):
                break
        if error or not hilo.is_alive() and rows:
            break
        await asyncio.sleep(0.2)
    if error:
        return JSONResponse({"doc_id": doc_id, "run_id": None, "estado_ingesta": "error", "error": error[0]},
                            status_code=500)
    return JSONResponse({"doc_id": doc_id, "run_id": run_id, "estado_ingesta": estado}, status_code=202)


@router.get("/documentos")
def listar_documentos() -> list[dict]:
    return db.query(f"SELECT {COLS_DOC} FROM documentos ORDER BY created_at DESC")


@router.get("/documentos/{doc_id}")
def detalle_documento(doc_id: str) -> dict:
    rows = db.query(f"SELECT {COLS_DOC}, archivo FROM documentos WHERE doc_id = ?", (doc_id,))
    if not rows:
        raise HTTPException(404, f"Documento {doc_id} no encontrado")
    doc = rows[0]
    doc["chunks"] = db.query("SELECT chunk_id, articulo, seccion, pagina, texto FROM chunks WHERE doc_id = ? "
                             "ORDER BY rowid", (doc_id,))
    doc["discrepancias"] = db.query(f"SELECT {COLS_DISC} FROM discrepancias WHERE doc_a = ? OR doc_b = ? "
                                    "ORDER BY id DESC", (doc_id, doc_id))
    return doc


@router.get("/discrepancias")
def listar_discrepancias(doc_id: str | None = None) -> list[dict]:
    if doc_id:
        return db.query(f"SELECT {COLS_DISC} FROM discrepancias WHERE doc_a = ? OR doc_b = ? ORDER BY id DESC",
                        (doc_id, doc_id))
    return db.query(f"SELECT {COLS_DISC} FROM discrepancias ORDER BY id DESC")


class Revision(BaseModel):
    decision: str
    comentario: str | None = None


@router.post("/discrepancias/{disc_id}/revisar")
def revisar_discrepancia(disc_id: int, body: Revision) -> dict:
    if body.decision not in ("confirmada", "descartada"):
        raise HTTPException(400, "decision debe ser 'confirmada' o 'descartada'")
    if not db.query("SELECT 1 FROM discrepancias WHERE id = ?", (disc_id,)):
        raise HTTPException(404, f"Discrepancia {disc_id} no encontrada")
    db.execute("UPDATE discrepancias SET estado_revision = ?, comentario = ? WHERE id = ?",
               (body.decision, body.comentario, disc_id))
    return {"ok": True}
