"""Endpoints del chat de casos (frente C, backend).

Contrato en docs/CONTRATOS.md (sección Chat de casos).
"""
from __future__ import annotations

import re
import time
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.concurrency import run_in_threadpool

from app.normas import db

router = APIRouter(tags=["chat"])

UPLOADS = db.ROOT / "data" / "uploads" / "casos"
CASOS_DIR = db.ROOT / "corpus" / "casos"
EXT_OK = {".pdf", ".docx", ".txt", ".md"}
MAX_BYTES = 10 * 1024 * 1024


@router.post("/chat")
async def chat(session_id: str = Form(...), mensaje: str = Form(""),
               archivo: UploadFile | None = File(None)) -> dict:
    from app.normas.casos import chat as chat_casos  # import diferido: registra las tools al usarse
    ruta: Path | None = None
    if archivo is not None and archivo.filename:
        ext = Path(archivo.filename).suffix.lower()
        if ext not in EXT_OK:
            raise HTTPException(400, f"Formato no soportado: {ext} (usa PDF, DOCX o TXT)")
        contenido = await archivo.read()
        if len(contenido) > MAX_BYTES:
            raise HTTPException(413, "Archivo demasiado grande (máx. 10 MB)")
        UPLOADS.mkdir(parents=True, exist_ok=True)
        nombre = re.sub(r"[^A-Za-z0-9._-]", "_", Path(archivo.filename).name)[-80:]
        ruta = UPLOADS / f"{int(time.time() * 1000)}_{nombre}"
        ruta.write_bytes(contenido)
    if not (mensaje or "").strip() and ruta is None:
        raise HTTPException(400, "Envía un mensaje o un archivo")
    return await run_in_threadpool(chat_casos, session_id, mensaje, ruta)


@router.get("/chat/ejemplos")
def ejemplos() -> list[dict]:
    out = []
    for p in sorted(CASOS_DIR.glob("*.txt")):
        texto = p.read_text(encoding="utf-8").strip()
        titulo = texto.splitlines()[0].strip() if texto else p.stem
        out.append({"id": p.stem, "titulo": titulo, "texto": texto})
    return out


@router.get("/chat/{session_id}")
def historial(session_id: str) -> list[dict]:
    from app.normas.casos import historial as hist
    return hist(session_id)
