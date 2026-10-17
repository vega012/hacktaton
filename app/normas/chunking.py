"""Chunking por artículo.

- Regex ^(Artículo|Art.) N -> un chunk por artículo; si supera 1500 caracteres se parte en c0, c1...
- Texto antes del primer artículo (encabezado/preámbulo) -> chunk art-0 "preámbulo".
- Sin artículos -> ventanas de 800 caracteres con solape 100, articulo = "sección N".
- id = "<doc_id>#art-<n>#c<k>"; `texto_indexado` lleva el prefijo [<nombre_norma> v<version> · Art. <n>].
"""
from __future__ import annotations

import re
from typing import Any

ART_RE = re.compile(r"^\s*(Art[íi]culo|Art\.)\s+(\d+)", re.IGNORECASE | re.MULTILINE)
MAX_ART = 1500
WIN, OVERLAP = 800, 100


def _partir(texto: str, size: int, overlap: int) -> list[str]:
    if len(texto) <= size:
        return [texto]
    out, i = [], 0
    while i < len(texto):
        out.append(texto[i:i + size])
        if i + size >= len(texto):
            break
        i += size - overlap
    return out


def _partir_articulo(texto: str) -> list[str]:
    """Parte un artículo largo por párrafos (o por tamaño si no hay párrafos)."""
    if len(texto) <= MAX_ART:
        return [texto]
    partes, actual = [], ""
    for par in re.split(r"\n\s*\n|\n", texto):
        if actual and len(actual) + len(par) + 1 > MAX_ART:
            partes.append(actual)
            actual = ""
        actual = f"{actual}\n{par}" if actual else par
    if actual:
        partes.append(actual)
    out: list[str] = []
    for p in partes:
        out.extend(_partir(p, MAX_ART, OVERLAP))
    return out


def _pagina_de(offset: int, cortes: list[tuple[int, int]]) -> int:
    pag = cortes[0][1] if cortes else 1
    for ini, p in cortes:
        if offset >= ini:
            pag = p
    return pag


def chunkear(paginas: list[tuple[int, str]], meta: dict[str, Any]) -> list[dict[str, Any]]:
    doc_id = meta["doc_id"]
    nombre = meta.get("nombre_norma") or doc_id
    version = meta.get("version") or "1"

    texto, cortes = "", []
    for pag, t in paginas:
        cortes.append((len(texto), pag))
        texto += t.rstrip() + "\n"

    chunks: list[dict[str, Any]] = []
    usados: set[str] = set()

    def agregar(n: str, articulo: str, seccion: str, cuerpo: str, offset: int) -> None:
        etiqueta = f"Art. {n}" if articulo.isdigit() else articulo
        for k, parte in enumerate(_partir_articulo(cuerpo.strip())):
            cid = f"{doc_id}#art-{n}#c{k}"
            while cid in usados:  # artículo repetido en el documento
                k += 1
                cid = f"{doc_id}#art-{n}#c{k}"
            usados.add(cid)
            chunks.append({
                "chunk_id": cid, "doc_id": doc_id, "articulo": articulo, "seccion": seccion,
                "pagina": _pagina_de(offset, cortes), "texto": parte,
                "texto_indexado": f"[{nombre} v{version} · {etiqueta}] {parte}",
            })

    matches = list(ART_RE.finditer(texto))
    if not matches:
        for i, w in enumerate(_partir(texto.strip(), WIN, OVERLAP), start=1):
            if w.strip():
                cid = f"{doc_id}#art-s{i}#c0"
                usados.add(cid)
                chunks.append({
                    "chunk_id": cid, "doc_id": doc_id, "articulo": f"sección {i}", "seccion": None,
                    "pagina": _pagina_de(texto.find(w), cortes), "texto": w.strip(),
                    "texto_indexado": f"[{nombre} v{version} · sección {i}] {w.strip()}",
                })
        return chunks

    pre = texto[: matches[0].start()].strip()
    if len(pre) > 40:
        agregar("0", "preámbulo", "Encabezado", pre, 0)
    for i, m in enumerate(matches):
        fin = matches[i + 1].start() if i + 1 < len(matches) else len(texto)
        cuerpo = texto[m.start():fin]
        primera = cuerpo.strip().split("\n", 1)[0]
        seccion = re.sub(r"^\s*(Art[íi]culo|Art\.)\s+\d+\s*[.:°º-]*\s*", "", primera, flags=re.I).strip()[:120]
        agregar(m.group(2), m.group(2), seccion or None, cuerpo, m.start())
    return chunks
