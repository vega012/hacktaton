"""Motor que lanza ejecuciones y aplica decisiones humanas (aprobar / rechazar)."""
from __future__ import annotations

import logging
from datetime import datetime

from app.agents.agent import Agent, AgentSession
from app.agents.trace import Run, RunStore, store as default_store

log = logging.getLogger("engine")

_STATUS = {"done": "completed", "failed": "failed", "waiting_approval": "waiting_approval", "running": "running"}


class Engine:
    def __init__(self, store: RunStore | None = None) -> None:
        self.store = store or default_store
        self.sessions: dict[str, AgentSession] = {}

    def start(self, agent: Agent, input_text: str, case: str = "demo") -> Run:
        run = self.store.create(case, input_text)
        session = AgentSession(agent, run, input_text)
        with self.store.lock:
            self.sessions[run.id] = session
            session.start()
            self._sync(run, session)
        return run

    def decide(self, approval_id: str, approved: bool, by: str = "humano", comment: str | None = None) -> Run:
        found = self.store.find_approval(approval_id)
        if not found:
            raise KeyError(f"Aprobación {approval_id} no encontrada")
        run, approval = found
        with self.store.lock:
            if approval.status != "pending":
                raise ValueError(f"La aprobación {approval_id} ya fue resuelta ({approval.status})")
            approval.status = "approved" if approved else "rejected"
            approval.decided_by = by
            approval.comment = comment
            approval.decided_at = datetime.now().isoformat(timespec="seconds")
            session = self.sessions[run.id]
            session.resolve_approval(approval)
            self._sync(run, session)
        return run

    def _sync(self, run: Run, session: AgentSession) -> None:
        run.status = _STATUS.get(session.status, run.status)
        if session.status == "done":
            run.output = session.output
        elif session.status == "failed":
            run.error = session.output
        self.store.save(run)


engine = Engine()
