"""Caso de ejemplo de punta a punta desde consola (sin UI).

Uso: python scripts/run_example.py [--rechazar]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import app.sector  # noqa: E402,F401  registra tools y validadores
from app.agents.engine import engine  # noqa: E402
from app.logging_config import setup_logging  # noqa: E402
from app.sector.agents import asistente  # noqa: E402

CASO = (
    "Revisa las entidades ENT-001 y ENT-002. A cada una que esté activa créale una orden de 3000 "
    "por 'mantenimiento preventivo'. Luego resume qué se hizo."
)


def print_trace(run) -> None:
    print(f"\n===== Traza run {run.id} | estado: {run.status} =====")
    for s in run.steps:
        print(f"#{s.n:02d} {s.ts[11:]} [{s.agent}] {s.type:<18} {s.summary}")
    if run.output:
        print(f"\n>>> Resultado final:\n{run.output}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--rechazar", action="store_true", help="rechazar en vez de aprobar")
    args = ap.parse_args()
    setup_logging("WARNING")

    run = engine.start(asistente, CASO, case="ejemplo")
    while run.status == "waiting_approval":
        for a in run.pending_approvals():
            print(f"\n*** Aprobación pendiente {a.id}: {a.tool}({a.arguments}) — {a.reason}")
            print_trace(run)
            ok = not args.rechazar
            print(f"\n*** Humano {'APRUEBA' if ok else 'RECHAZA'} {a.id}")
            run = engine.decide(a.id, approved=ok, by="supervisor", comment=None if ok else "Monto no presupuestado")
    print_trace(run)
    return 0 if run.status == "completed" else 1


if __name__ == "__main__":
    sys.exit(main())
