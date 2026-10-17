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

tabs = st.tabs(["💬 Consultar", "📑 Normas", "⚖️ Discrepancias", "🔎 Trazas", "📊 Dashboard", "🎯 KPIs"])

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

# ------------------------------------------------------------------ KPIs
SD = "sin datos"


def _g(d, *keys, default=None):
    """Acceso seguro a dicts anidados (tolera None / tipos inesperados)."""
    for k in keys:
        if not isinstance(d, dict):
            return default
        d = d.get(k)
    return default if d is None else d


def _pct(v) -> str:
    try:
        return SD if v is None else f"{float(v) * 100:.1f} %"
    except (TypeError, ValueError):
        return SD


def _num(v, fmt="{:.1f}", suf="") -> str:
    try:
        return SD if v is None else fmt.format(float(v)) + suf
    except (TypeError, ValueError):
        return SD


def _desglose(d) -> str:
    d = d if isinstance(d, dict) else {}
    return " · ".join(f"{k}: {v}" for k, v in d.items()) if d else SD


def _lista(x):
    return ", ".join(map(str, x)) if isinstance(x, list) else x


def _kpi_pct(col, titulo: str, k, unidad: str = "consultas", extra: str | None = None) -> None:
    with col.container(border=True):
        st.metric(titulo, _pct(_g(k, "valor")))
        num, den = _g(k, "num", default=0), _g(k, "den", default=0)
        st.caption(f"{num} de {den} {unidad}" if den else f"0 de 0 {unidad} · {SD}")
        if extra:
            st.caption(extra)


def _df(rows, cols: list[str]):
    if not isinstance(rows, list) or not rows:
        return None
    df = pd.DataFrame([r for r in rows if isinstance(r, dict)])
    if df.empty:
        return None
    sel = [c for c in cols if c in df.columns]
    return df[sel] if sel else df


def fetch_kpis(params: dict):
    """GET /api/kpis; devuelve (datos, error). Nunca lanza."""
    return api("GET", "/kpis", params=params, timeout=60)


with tabs[5]:
    import datetime as _dt

    st.subheader("🎯 KPIs · valor medible de los agentes")
    hoy = _dt.date.today()
    f = st.columns([1, 1, 1, 1, 1.3])
    desde = f[0].date_input("Desde", value=hoy, key="k_desde")
    hasta = f[1].date_input("Hasta", value=hoy, key="k_hasta")
    gran = f[2].selectbox("Granularidad tendencia", ["10min", "hora", "dia"], index=1, key="k_gran")
    umbral_txt = f[3].text_input("Umbral de score (vacío = backend)", value="", key="k_umbral")
    t_manual = f[4].number_input("Tiempo manual de referencia (min)", min_value=0.0, value=15.0, step=1.0,
                                 key="k_tman")
    params = {"desde": str(desde), "hasta": str(hasta), "granularidad": gran, "tiempo_manual_min": t_manual}
    if umbral_txt.strip():
        try:
            params["umbral"] = float(umbral_txt.replace(",", "."))
        except ValueError:
            st.warning("Umbral inválido: se usa el del backend.")

    try:
        kp, err = fetch_kpis(params)
    except Exception as e:  # el fetch no debería lanzar, pero por si acaso
        kp, err = None, f"{type(e).__name__}: {e}"
    if err or not isinstance(kp, dict):
        st.warning(f"No se pudieron cargar los KPIs: {err or 'respuesta inválida'}")
        kp = {}
    try:
        cal, prev = _g(kp, "calidad", default={}), _g(kp, "prevencion", default={})
        efi, traz = _g(kp, "eficiencia", default={}), _g(kp, "trazabilidad", default={})
        tend = _g(kp, "tendencia", default={})
        total = _g(cal, "total_consultas", default=0)
        st.info(f"Backend de búsqueda: **{_g(kp, 'backend', default=SD)}** · umbral usado: "
                f"**{_g(kp, 'umbral', default='el del backend')}** · consultas en el rango: **{total}** "
                f"({_desglose(_g(cal, 'por_tipo'))}) · generado: {_g(kp, 'generado_at', default=SD)}")
        if not total:
            st.warning("Sin consultas registradas en el rango: los indicadores muestran «sin datos» "
                       "(no se inventan cifras).")

        AGENTE1 = ["validador"]
        AGENTE2 = ["consultas", "analista_casos"]
        tr = _g(efi, "tiempo_respuesta_s", default={})
        pa = _g(tr, "por_agente", default={})
        pa = pa if isinstance(pa, dict) else {}
        tc = _g(traz, "trazas_completas", default={})
        tc_pa = _g(tc, "por_agente", default={})
        tc_pa = tc_pa if isinstance(tc_pa, dict) else {}
        inc = _g(tc, "incompletas", default=[])
        inc = inc if isinstance(inc, list) else []

        def _tiempos(agentes: list[str], col) -> None:
            """KPI 8 para un grupo de agentes: promedio ponderado por n, desde la traza."""
            filas = [{"agente": a, "promedio_s": _g(pa[a], "promedio"), "mediana_s": _g(pa[a], "mediana"),
                      "n": _g(pa[a], "n", default=0)} for a in agentes if a in pa]
            con = [f for f in filas if f["promedio_s"] is not None and f["n"]]
            n = sum(f["n"] for f in con)
            prom = sum(f["promedio_s"] * f["n"] for f in con) / n if n else None
            with col.container(border=True):
                st.metric("8 · Tiempo promedio de respuesta", _num(prom, suf=" s"))
                st.caption(f"medido en la traza (inicio → fin) · n = {n}")
                if filas:
                    st.dataframe(pd.DataFrame(filas), width="stretch", hide_index=True)

        def _trazas(agentes: list[str], col) -> None:
            """KPI 10 para un grupo de agentes."""
            num = sum(_g(tc_pa.get(a), "num", default=0) for a in agentes)
            den = sum(_g(tc_pa.get(a), "den", default=0) for a in agentes)
            _kpi_pct(col, "10 · Trazas completas (objetivo 100 %)", {"valor": num / den if den else None,
                                                                      "num": num, "den": den},
                     unidad="ejecuciones")
            mias = [x for x in inc if isinstance(x, dict) and x.get("agente") in agentes]
            with col.expander(f"Trazas incompletas ({len(mias)})"):
                dfi = _df(mias, ["run_id", "agente", "faltan"])
                if dfi is not None:
                    if "faltan" in dfi.columns:
                        dfi["faltan"] = dfi["faltan"].apply(_lista)
                    st.dataframe(dfi, width="stretch", hide_index=True)
                else:
                    st.caption("ninguna")

        tab1, tab2, tab3 = st.tabs(["🧾 Agente 1 · Ingesta y validación",
                                    "💬 Agente 2 · Chat de consultas y casos", "📐 Cómo se calcula"])

        # ================================================================ Agente 1
        with tab1:
            st.caption("Agente validador: revisa cada norma cargada contra el corpus y registra contradicciones "
                       "y actualizaciones. Valor de prevención.")
            b = st.columns(3)
            disc = _g(prev, "discrepancias", default={})
            with b[0].container(border=True):
                st.metric("5 · Discrepancias detectadas", _g(disc, "total", default=0))
                st.caption(f"por severidad: {_desglose(_g(disc, 'por_severidad'))}")
                st.caption(f"por tipo: {_desglose(_g(disc, 'por_tipo'))}")
                ps = _g(disc, "por_severidad", default={})
                if isinstance(ps, dict) and ps:
                    st.bar_chart(pd.Series(ps, name="discrepancias"))
            obs = _g(prev, "normas_obsoletas", default={})
            with b[1].container(border=True):
                st.metric("6 · Normas obsoletas o reemplazadas", _g(obs, "total", default=0))
                dfo = _df(_g(obs, "lista"), ["doc_id", "nombre_norma", "estado", "reemplazada_por"])
                if dfo is not None:
                    st.dataframe(dfo, width="stretch", hide_index=True)
                else:
                    st.caption(SD)
            with b[2].container(border=True):
                st.markdown("**7 · Documentos afectados por norma**")
                dfa = _df(_g(prev, "afectados_por_norma"), ["nombre_norma", "doc_id", "n", "afectados"])
                if dfa is not None:
                    if "afectados" in dfa.columns:
                        dfa["afectados"] = dfa["afectados"].apply(_lista)
                    st.dataframe(dfa, width="stretch", hide_index=True)
                else:
                    st.caption(SD)
            e1 = st.columns(2)
            _tiempos(AGENTE1, e1[0])
            _trazas(AGENTE1, e1[1])

        # ================================================================ Agente 2
        with tab2:
            st.caption("Agente de consultas y agente analista de casos (chat): calidad de las respuestas, "
                       "eficiencia, trazabilidad y brechas normativas.")
            st.markdown("#### Calidad de las respuestas")
            a = st.columns(4)
            _kpi_pct(a[0], "1 · Con cita verificable", _g(cal, "con_cita"))
            sc = _g(cal, "sin_cobertura", default={})
            _kpi_pct(a[1], "2 · Sin cobertura", sc,
                     extra=f"no encontró: {_g(sc, 'no_encontro', default=0)} · score bajo: "
                           f"{_g(sc, 'score_bajo', default=0)}")
            ad = _g(cal, "con_advertencia", default={})
            _kpi_pct(a[2], "3 · Con advertencia", ad,
                     extra=f"conflicto: {_g(ad, 'conflicto', default=0)} · obsoleta: {_g(ad, 'obsoleta', default=0)}")
            cp = _g(cal, "confianza_promedio", default={})
            with a[3].container(border=True):
                st.metric("4 · Confianza promedio", _num(_g(cp, "valor"), "{:.2f}"))
                st.caption(f"sobre {_g(cp, 'n', default=0)} consultas")
                dist = _g(cp, "distribucion", default={})
                if isinstance(dist, dict) and dist:
                    st.caption(f"🟢 alta: {dist.get('alta', 0)} · 🟡 media: {dist.get('media', 0)} · "
                               f"🔴 sin respaldo: {dist.get('sin_respaldo', 0)}")
                else:
                    st.caption(f"distribución: {SD}")

            st.markdown("#### Eficiencia y trazabilidad")
            c = st.columns(3)
            _tiempos(AGENTE2, c[0])
            ta = _g(efi, "tiempo_ahorrado", default={})
            with c[1].container(border=True):
                st.markdown("<span class='badge' style='background:#b26a00'>ESTIMADO · supuesto editable</span>",
                            unsafe_allow_html=True)
                st.metric("9 · Tiempo ahorrado (estimado)", _num(_g(ta, "horas"), suf=" h"))
                st.caption(f"Supuesto: {_g(ta, 'supuesto', default=SD)}")
                st.caption(f"= {_g(ta, 'consultas', default=0)} consultas × "
                           f"({_g(ta, 'tiempo_manual_min', default=t_manual)} min − tiempo promedio del agente). "
                           "No es una medición: ajusta el tiempo manual arriba.")
            _trazas(AGENTE2, c[2])

            st.markdown("#### Normas consultadas y brechas")
            g = st.columns(2)
            with g[0].container(border=True):
                st.markdown("**11 · Top 10 normas más consultadas**")
                dft = _df(_g(traz, "top_normas"), ["nombre_norma", "doc_id", "n"])
                if dft is not None and "n" in dft.columns:
                    dft = dft.head(10)
                    idx = "nombre_norma" if "nombre_norma" in dft.columns else dft.columns[0]
                    st.bar_chart(dft.set_index(idx)["n"], horizontal=True)
                else:
                    st.caption(SD)
            with g[1].container(border=True):
                st.markdown("**11 · Normas que faltan (brechas por tema)**")
                dfb = _df(_g(tend, "brechas_por_tema"), ["tema", "n"])
                if dfb is not None and {"tema", "n"} <= set(dfb.columns):
                    st.bar_chart(dfb.set_index("tema")["n"])
                br = _g(traz, "brechas", default=[])
                if isinstance(br, list) and br:
                    with st.expander("Ejemplos por tema"):
                        for x in br:
                            if isinstance(x, dict):
                                st.markdown(f"**{x.get('tema', '?')}** · {x.get('n', 0)}")
                                for ej in (x.get("ejemplos") or [])[:3]:
                                    st.caption(f"• {ej}")
                else:
                    st.caption(SD)

            st.markdown(f"#### Tendencia de consultas ({_g(tend, 'granularidad', default=gran)})")
            dfc = _df(_g(tend, "consultas"), ["t", "n", "sin_cobertura"])
            ycols = [x for x in ["n", "sin_cobertura"] if dfc is not None and x in dfc.columns]
            if dfc is not None and "t" in dfc.columns and ycols:
                # barras: con un solo bucket una línea no se dibuja
                st.bar_chart(dfc.set_index("t")[ycols], stack=False)
            else:
                st.caption(SD)

        # ================================================================ Cómo se calcula
        with tab3:
            st.markdown(
                "Fuente: consultas, trazas, discrepancias y documentos registrados por los agentes en el rango "
                "filtrado. `null` ⇒ «sin datos».\n\n"
                "1. **% con cita verificable** = consultas con ≥1 cita verificada / total de consultas.\n"
                "2. **% sin cobertura** = consultas sin respaldo / total; desglose *no_encontro* (búsqueda sin "
                "resultados) y *score_bajo* (mejor score < umbral).\n"
                "3. **% con advertencia** = consultas con ≥1 advertencia / total; desglose *conflicto* "
                "(discrepancia entre normas) y *obsoleta* (norma no vigente involucrada).\n"
                "4. **Confianza promedio** = promedio sobre las n consultas con respaldo; distribución por nivel "
                "alta / media / sin_respaldo.\n"
                "5. **Discrepancias** = registros del agente validador, por severidad y por tipo.\n"
                "6. **Normas obsoletas** = documentos no vigentes (reemplazada / derogada) con su reemplazo.\n"
                "7. **Documentos afectados por norma** = documentos que referencian cada norma afectada.\n"
                "8. **Tiempo de respuesta** = latencia registrada en la traza (s): promedio y mediana, total y por "
                "agente.\n"
                "9. **Tiempo ahorrado (ESTIMADO)** = consultas × (tiempo manual de referencia − tiempo promedio "
                "del agente). El tiempo manual es un supuesto editable, no una medición.\n"
                "10. **% trazas completas** = ejecuciones con traza completa / ejecuciones; objetivo 100 %. Las "
                "incompletas indican qué falta.\n"
                "11. **Top normas** = normas más citadas (top 10); **brechas** = temas consultados sin cobertura, "
                "con conteo y ejemplos.")
    except Exception as e:  # nunca romper la pestaña ante una forma inesperada
        st.warning(f"Los KPIs llegaron con un formato inesperado: {type(e).__name__}: {e}")
