"""Carga el corpus de demo (corpus/) con metadatos deterministas y espera cada validación.

    .venv/Scripts/python scripts/seed_corpus.py --reset         # SINT-01, SINT-02, SBS-EJ-01, SBS-EJ-02
    .venv/Scripts/python scripts/seed_corpus.py --reset --all   # además SINT-03 (normalmente se sube en vivo)
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.normas import db  # noqa: E402
from app.normas.ingesta import ingerir  # noqa: E402
from app.normas.vector import get_store  # noqa: E402

ORDEN = ["SINT-01.txt", "SINT-02.txt", "SBS-EJ-01.txt", "SBS-EJ-02.txt"]


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true", help="borra namespace y tablas de documentos")
    ap.add_argument("--all", action="store_true", help="incluye SINT-03 (contradicción deliberada)")
    ap.add_argument("--sin-validar", action="store_true", help="no lanza el agente validador")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    for noisy in ("httpx", "openai", "agent", "engine", "trace"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    store = get_store()
    print(f"Vector store: {store.backend}")
    if args.reset:
        store.delete_all()
        with db.connect() as con:
            for t in ("discrepancias", "chunks_fts", "chunks", "documentos"):
                con.execute(f"DELETE FROM {t}")
            con.execute("DELETE FROM sqlite_sequence WHERE name = 'discrepancias'")
        print("Reset: namespace y tablas borrados")

    metas = json.loads((ROOT / "corpus" / "metadatos.json").read_text(encoding="utf-8"))
    archivos = ORDEN + (["SINT-03.txt"] if args.all else [])
    for nombre in archivos:
        t0 = time.time()
        doc_id = ingerir(ROOT / "corpus" / nombre, metadatos=metas[nombre], validar=not args.sin_validar,
                         esperar=True, usuario="seed", canal="script")
        n = db.query("SELECT COUNT(*) n FROM discrepancias WHERE doc_a = ?", (doc_id,))[0]["n"]
        print(f"  {nombre} -> {doc_id}  ({time.time() - t0:.1f}s, {n} discrepancias nuevas)")
        if store.backend == "pinecone":
            time.sleep(3)  # consistencia eventual de Pinecone antes del siguiente documento

    print("\nDocumentos:")
    for d in db.query("SELECT doc_id, nombre_norma, version, estado, estado_ingesta, n_chunks, run_id "
                      "FROM documentos ORDER BY created_at"):
        print(f"  {d['doc_id']:<10} v{d['version']} {d['estado']:<24} {d['estado_ingesta']:<10} "
              f"chunks={d['n_chunks']:<3} run={d['run_id']}  {d['nombre_norma']}")
    print("\nDiscrepancias:")
    for x in db.query("SELECT * FROM discrepancias ORDER BY id"):
        print(f"  #{x['id']} [{x['tipo']}/{x['severidad']}] {x['chunk_a']}  vs  {x['chunk_b']}")
        print(f"      a: {x['cita_a']}\n      b: {x['cita_b']}\n      {x['explicacion']}")


if __name__ == "__main__":
    main()
