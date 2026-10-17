"""Motor que lanza ejecuciones y aplica decisiones humanas (aprobar / rechazar).

Con `background=True` el trabajo corre en un hilo y el Run se puede consultar mientras avanza
(lo usa la API / UI). Sin background es síncrono (lo usan los scripts).
"""
from __future__ import annotations

import logging
import threading
from datetime import datetime
from typing import Callable

from app.agents.agent import Agent, AgentSession
from app.agents.trace import Run, RunStore, store as default_store

log = logging.getLogger("engine")

_STATUS = {"done": "completed", "failed": "failed", "waiting_approval": "waiting_approval", "running": "running"}


class Engine:
    def __init__(self, store: RunStore | None = None) -> None:
        self.store = store or default_store
        self.sessions: dict[str, AgentSession] = {}
        self._locks: dict[str, threading.Lock] = {}

    def start(self, agent: Agent, input_text: str, case: str = "demo", background: bool = False) -> Run:
        run = self.store.create(case, input_text)
        session = AgentSession(agent, run, input_text)
        self.sessions[run.id] = session
        self._locks[run.id] = threading.Lock()
        self._dispatch(run, session, session.start, background)
        return run

    def decide(self, approval_id: str, approved: bool, by: str = "humano", comment: str | None = None,
               background: bool = False) -> Run:
        found = self.store.find_approval(approval_id)
        if not found:
            raise KeyError(f"Aprobación {approval_id} no encontrada")
        run, approval = found
        with self.store.lock:  # evita doble decisión (doble clic)
            if approval.status != "pending":
                raise ValueError(f"La aprobación {approval_id} ya fue resuelta ({approval.status})")
            approval.status = "approved" if approved else "rejected"
            approval.decided_by = by
            approval.comment = comment
            approval.decided_at = datetime.now().isoformat(timespec="seconds")
        session = self.sessions[run.id]
        run.status = "running"
        self._dispatch(run, session, lambda: session.resolve_approval(approval), background)
        return run

    def _dispatch(self, run: Run, session: AgentSession, fn: Callable[[], object], background: bool) -> None:
        def work() -> None:
            with self._locks[run.id]:
                try:
                    fn()
                except Exception as e:  # nunca dejar un run colgado en "running"
                    log.exception("Error interno en run %s", run.id)
                    run.add_step("engine", "error", f"Error interno: {e}")
                    session.status, session.output = "failed", str(e)
                self._sync(run, session)

        if background:
            threading.Thread(target=work, name=f"run-{run.id}", daemon=True).start()
        else:
            work()

    def _sync(self, run: Run, session: AgentSession) -> None:
        run.status = _STATUS.get(session.status, run.status)
        if session.status == "done":
            run.output = session.output
        elif session.status == "failed":
            run.error = session.output
        self.store.save(run)


engine = Engine()
