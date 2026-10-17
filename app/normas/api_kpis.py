"""Endpoint de KPIs. MOCK: reemplazar por la implementación real (app/normas/kpis.py).

Contrato en docs/CONTRATOS.md (sección KPIs). Todo null = sin datos.
"""
from fastapi import APIRouter

router = APIRouter(tags=["kpis"])

_SD = {"valor": None, "num": 0, "den": 0}


@router.get("/kpis")
def kpis(desde: str | None = None, hasta: str | None = None, umbral: float | None = None,
         tiempo_manual_min: float = 15, granularidad: str = "hora") -> dict:
    return {
        "rango": {"desde": desde, "hasta": hasta}, "backend": "local", "umbral": umbral, "generado_at": None,
        "calidad": {"total_consultas": 0, "por_tipo": {}, "con_cita": _SD,
                    "sin_cobertura": {**_SD, "no_encontro": 0, "score_bajo": 0},
                    "con_advertencia": {**_SD, "conflicto": 0, "obsoleta": 0},
                    "confianza_promedio": {"valor": None, "n": 0, "distribucion": {}}},
        "prevencion": {"discrepancias": {"total": 0, "por_severidad": {}, "por_tipo": {}},
                       "normas_obsoletas": {"total": 0, "lista": []}, "afectados_por_norma": []},
        "eficiencia": {"tiempo_respuesta_s": {"promedio": None, "mediana": None, "n": 0, "por_agente": {}},
                       "tiempo_ahorrado": {"estimado": True, "tiempo_manual_min": tiempo_manual_min, "consultas": 0,
                                           "horas": None, "supuesto": "consultas × (tiempo manual de referencia − "
                                                                      "tiempo promedio del agente)"}},
        "trazabilidad": {"trazas_completas": {**_SD, "incompletas": []}, "top_normas": [], "brechas": []},
        "tendencia": {"granularidad": granularidad, "consultas": [], "brechas_por_tema": []},
    }
