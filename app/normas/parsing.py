"""Extracción de texto por página: PDF (pypdf, respaldo pdfplumber), DOCX (python-docx) y TXT.

    paginas, requiere_revision, motivo = parsear(path)
    paginas = [(1, "texto página 1"), (2, "...")]
"""
from __future__ import annotations

import logging
import re
from pathlib import Path

log = logging.getLogger("parsing")

ART_RE = re.compile(r"^\s*(Art[íi]culo|Art\.)\s+\d+", re.IGNORECASE | re.MULTILINE)


def _pdf(path: Path) -> list[tuple[int, str]]:
    try:
        from pypdf import PdfReader

        pages = [(i + 1, p.extract_text() or "") for i, p in enumerate(PdfReader(str(path)).pages)]
        if sum(len(t.strip()) for _, t in pages) > 50:
            return pages
        log.warning("pypdf extrajo poco texto de %s; se intenta pdfplumber", path.name)
    except Exception as e:
        log.warning("pypdf falló con %s: %s; se intenta pdfplumber", path.name, e)
    import pdfplumber

    with pdfplumber.open(str(path)) as pdf:
        return [(i + 1, p.extract_text() or "") for i, p in enumerate(pdf.pages)]


def _docx(path: Path) -> list[tuple[int, str]]:
    import docx

    d = docx.Document(str(path))
    lines = [p.text for p in d.paragraphs]
    for table in d.tables:
        for row in table.rows:
            lines.append(" | ".join(c.text for c in row.cells))
    return [(1, "\n".join(lines))]


def _txt(path: Path) -> list[tuple[int, str]]:
    raw = path.read_bytes()
    for enc in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    # \f (salto de página) separa páginas si existe
    return [(i + 1, t) for i, t in enumerate(text.split("\f"))]


def es_basura(texto: str) -> tuple[bool, str]:
    """Heurística: >30% de caracteres no alfabéticos (sin contar espacios) o sin artículos."""
    sin_esp = re.sub(r"\s", "", texto)
    if len(sin_esp) < 50:
        return True, "Texto vacío o casi vacío (¿PDF escaneado sin OCR?)"
    no_alfa = sum(1 for c in sin_esp if not c.isalpha())
    if no_alfa / len(sin_esp) > 0.30:
        return True, f"{no_alfa / len(sin_esp):.0%} de caracteres no alfabéticos"
    if not ART_RE.search(texto):
        return True, "No se detectaron artículos numerados"
    return False, ""


def parsear(path: str | Path) -> tuple[list[tuple[int, str]], bool, str]:
    path = Path(path)
    ext = path.suffix.lower()
    if ext == ".pdf":
        pages = _pdf(path)
    elif ext == ".docx":
        pages = _docx(path)
    elif ext in (".txt", ".md", ""):
        pages = _txt(path)
    else:
        raise ValueError(f"Formato no soportado: {ext} (usa PDF, DOCX o TXT)")
    basura, motivo = es_basura("\n".join(t for _, t in pages))
    return pages, basura, motivo
