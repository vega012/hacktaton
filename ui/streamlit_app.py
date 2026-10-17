"""Interfaz Streamlit (cliente delgado de la API). Plan B del bot y consola de revisión.

Uso:  .venv/Scripts/streamlit run ui/streamlit_app.py --server.port 8501
API:  API_BASE_URL (env o .env), por defecto http://127.0.0.1:8000
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pandas as pd
import requests
import streamlit as st

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
try:
    from app.config import get_settings
    API = os.environ.get("API_BASE_URL") or get_settings().api_base_url
except Exception:
    API = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000")
API = API.rstrip("/") + "/api"

st.set_page_config(page_title="Normativa Bancaria · Agentes de IA", page_icon="📚", layout="wide")
st.markdown("""<style>
html, body, [class*="css"] { font-size: 19px; }
.stTabs [data-baseweb="tab"] { font-size: 1.15rem; font-weight: 600; }
.badge { padding: 2px 10px; border-radius: 10px; color: white; font-weight: 600; }
</style>""", unsafe_allow_html=True)

COLOR_ESTADO = {"vigente": "#1b8a3a", "reemplazada": "#b26a00", "derogada": "#b00020",
                "por_entrar_en_vigencia": "#1f5fbf"}
CONF = {"alta": ("🟢 Confianza alta", "success"), "media": ("🟡 Confianza media", "warning"),
        "sin_respaldo": ("🔴 Sin respaldo normativo", "error")}


def api(method: str, path: str, **kw):
    """Llama a la API; devuelve (datos, error). Nunca lanza excepción."""
    try:
        r = requests.request(method, API + path, timeout=kw.pop("timeout", 30), **kw)
        if r.status_code >= 400:
            return None, f"HTTP {r.status_code}: {r.text[:300]}"
        return r.json(), None
    except Exception as e:
        return None, f"{type(e).__name__}: {e}"


def badge(estado: str | None) -> str:
    c = COLOR_ESTADO.get(estado or "", "#666")
    return f"<span class='badge' style='background:{c}'>{estado or '?'}</span>"


def mostrar_respuesta(r: dict) -> None:
    st.markdown(r.get("respuesta", ""))
    txt, kind = CONF.get(r.get("confianza"), (str(r.get("confianza")), "info"))
    getattr(st, kind)(f"{txt} · score {r.get('top_score')} · {r.get('latencia_ms')} ms · run {r.get('run_id')}")
    for a in r.get("advertencias") or []:
        st.warning(f"⚠️ {a}")
    for c in r.get("citas") or []:
        with st.expander(f"📄 {c.get('nombre_norma')} · Art. {c.get('articulo')} · v{c.get('version')} · "
                         f"{c.get('estado')}"):
            if c.get("cita_literal"):
                st.markdown(f"> {c['cita_literal']}")
            st.caption(c.get("texto", ""))
            st.caption(f"chunk: {c.get('chunk_id', '')}")


st.title("📚 Normativa Bancaria · Agentes de IA")
st.caption(f"API: {API}")

tabs = st.tabs(["💬 Consultar", "📑 Normas", "⚖️ Discrepancias", "🔎 Trazas", "📊 Dashboard"])

# ------------------------------------------------------------------ Consultar
with tabs[0]:
    if "chat" not in st.session_state:
        st.session_state.chat = []
    for m in st.session_state.chat:
        with st.chat_message(m["role"]):
            if m["role"] == "user":
                st.markdown(m["content"])
            else:
                mostrar_respuesta(m["content"]) if isinstance(m["content"], dict) else st.error(m["content"])
    pregunta = st.chat_input("Escribe tu consulta normativa…")
    if pregunta:
        st.session_state.chat.append({"role": "user", "content": pregunta})
        with st.chat_message("user"):
            st.markdown(pregunta)
        with st.chat_message("assistant"):
            with st.spinner("Buscando en la normativa vigente…"):
                r, err = api("POST", "/consultas", json={"pregunta": pregunta, "canal": "web",
                                                         "usuario": "web:streamlit"}, timeout=120)
            if err:
                st.error(f"No se pudo consultar: {err}")
                st.session_state.chat.append({"role": "assistant", "content": f"Error: {err}"})
            else:
                mostrar_respuesta(r)
                st.session_state.chat.append({"role": "assistant", "content": r})

# ------------------------------------------------------------------ Normas
with tabs[1]:
    st.subheader("Cargar norma")
    archivo = st.file_uploader("PDF, DOCX o TXT", type=["pdf", "docx", "txt", "md"])
    if archivo and st.button("Subir e indexar", type="primary"):
        with st.spinner("Enviando documento…"):
            r, err = api("POST", "/documentos", files={"archivo": (archivo.name, archivo.getvalue())}, timeout=180)
        st.error(err) if err else st.success(f"Recibido: {r}")
    st.subheader("Normas registradas")
    if st.button("🔄 Actualizar", key="ref_docs"):
        st.rerun()
    docs, err = api("GET", "/documentos")
    if err:
        st.warning(f"El servicio de documentos no está disponible: {err}")
    elif not docs:
        st.info("Aún no hay normas registradas.")
    else:
        df = pd.DataFrame(docs)

        def _color(v):
            return f"background-color: {COLOR_ESTADO.get(v, '')}; color: white" if v in COLOR_ESTADO else ""
        cols = [c for c in ["doc_id", "nombre_norma", "version", "estado", "tipo", "tema", "fecha_vigencia",
                            "reemplaza_a", "n_chunks", "estado_ingesta"] if c in df.columns]
        st.dataframe(df[cols].style.map(_color, subset=["estado"] if "estado" in cols else []),
                     width="stretch", hide_index=True)

# ------------------------------------------------------------------ Discrepancias
with tabs[2]:
    st.subheader("Discrepancias detectadas")
    ds, err = api("GET", "/discrepancias")
    if err:
        st.warning(f"El servicio de discrepancias no está disponible: {err}")
    elif not ds:
        st.info("No hay discrepancias registradas.")
    else:
        for d in ds:
            icon = {"alta": "🔴", "media": "🟡", "baja": "🟢"}.get(d.get("severidad"), "⚪")
            with st.container(border=True):
                st.markdown(f"### {icon} #{d.get('id')} · {d.get('tipo')} · severidad {d.get('severidad')} · "
                            f"estado: **{d.get('estado_revision')}**")
                a, b = st.columns(2)
                a.markdown(f"**{d.get('doc_a')}**\n\n> {d.get('cita_a') or ''}")
                b.markdown(f"**{d.get('doc_b')}**\n\n> {d.get('cita_b') or ''}")
                st.markdown(f"*{d.get('explicacion') or ''}*")
                if d.get("estado_revision") == "pendiente":
                    com = st.text_input("Comentario", key=f"com_{d.get('id')}")
                    c1, c2, _ = st.columns([1, 1, 4])
                    for col, dec, lbl in ((c1, "confirmada", "✅ Confirmar"), (c2, "descartada", "❌ Descartar")):
                        if col.button(lbl, key=f"{dec}_{d.get('id')}"):
                            _, e2 = api("POST", f"/discrepancias/{d.get('id')}/revisar",
                                        json={"decision": dec, "comentario": com})
                            st.error(e2) if e2 else st.rerun()

# ------------------------------------------------------------------ Trazas
with tabs[3]:
    st.subheader("Trazas de ejecución de agentes")
    ts, err = api("GET", "/trazas", params={"limit": 50})
    if err:
        st.warning(f"No se pudieron cargar las trazas: {err}")
    elif not ts:
        st.info("Aún no hay trazas.")
    else:
        df = pd.DataFrame(ts)
        st.dataframe(df[[c for c in ["created_at", "run_id", "agente", "canal", "usuario", "entrada", "estado",
                                     "latencia_ms"] if c in df.columns]], width="stretch", hide_index=True)
        opciones = {f"{t['run_id']} · {t.get('agente')} · {(t.get('entrada') or '')[:60]}": t["run_id"] for t in ts}
        sel = st.selectbox("Ver detalle", list(opciones))
        if sel:
            det, err = api("GET", f"/trazas/{opciones[sel]}")
            if err:
                st.warning(err)
            else:
                st.markdown(f"**Entrada:** {det.get('entrada')}")
                st.markdown(f"**Salida:** {det.get('salida')}")
                st.caption(f"modelo {det.get('modelo')} · {det.get('latencia_ms')} ms · {det.get('estado')}")
                ICON = {"input": "📥", "thought": "💭", "tool_call": "🛠️", "tool_result": "📦", "final": "✅",
                        "error": "❌", "verificacion": "🧪", "handoff": "🔀", "guardrail": "🛡️"}
                for p in det.get("pasos", []):
                    data = p.get("data") or {}
                    with st.expander(f"{ICON.get(p.get('type'), '•')} #{p.get('n')} {p.get('agent')} / "
                                     f"{p.get('type')}: {p.get('summary', '')[:110]}"):
                        if p.get("type") == "tool_call":
                            st.json(data.get("arguments", {}))
                        elif p.get("type") == "tool_result":
                            res = data.get("result", {})
                            hits = res.get("hits") or res.get("no_vigentes") or res.get("fragmentos")
                            if hits:
                                st.dataframe(pd.DataFrame(hits)[[c for c in ["id", "best_score", "score",
                                             "rerank_score", "doc_id", "articulo", "version", "estado"]
                                             if c in pd.DataFrame(hits).columns]],
                                             width="stretch", hide_index=True)
                            else:
                                st.json(res)
                        else:
                            st.write(data.get("full") or p.get("summary"))
                if det.get("consulta"):
                    st.markdown("**Resultado verificado**")
                    st.json(det["consulta"], expanded=False)

# ------------------------------------------------------------------ Dashboard
with tabs[4]:
    dash, err = api("GET", "/dashboard")
    if err:
        st.warning(f"No se pudo cargar el dashboard: {err}")
    else:
        u = dash.get("uso", {})
        m = st.columns(6)
        m[0].metric("Consultas", u.get("consultas_total", 0))
        m[1].metric("Hoy", u.get("consultas_hoy", 0))
        m[2].metric("% cubiertas", f"{u.get('pct_cubiertas', 0)}%")
        m[3].metric("Latencia p50", f"{u.get('latencia_p50_ms', 0)} ms")
        m[4].metric("Documentos", u.get("documentos", 0))
        m[5].metric("Fragmentos", u.get("chunks", 0))
        c1, c2 = st.columns(2)
        with c1:
            st.subheader("Normas más consultadas")
            tn = dash.get("top_normas") or []
            if tn:
                st.bar_chart(pd.DataFrame(tn).set_index("nombre_norma")["n"], horizontal=True)
            else:
                st.info("Sin datos aún.")
        with c2:
            st.subheader("Temas sin cobertura")
            sc = dash.get("sin_cobertura") or []
            if not sc:
                st.info("Todas las consultas tuvieron respaldo.")
            for s in sc:
                st.markdown(f"**{s['tema']}** · {s['n']} consulta(s)")
                for ej in s.get("ejemplos", []):
                    st.caption(f"• {ej}")
        disc = dash.get("discrepancias", {})
        st.subheader(f"Discrepancias activas: {disc.get('total', 0)}")
        if disc.get("por_tipo"):
            st.bar_chart(pd.Series(disc["por_tipo"], name="n"))
        if disc.get("recientes"):
            st.dataframe(pd.DataFrame(disc["recientes"]), width="stretch", hide_index=True)
