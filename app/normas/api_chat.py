"""Endpoints del chat de casos (frente C, backend). MOCK: reemplazar por la implementación real.

Contrato en docs/CONTRATOS.md (sección Chat de casos).
"""
from fastapi import APIRouter, File, Form, UploadFile

router = APIRouter(tags=["chat"])


@router.post("/chat")
async def chat(session_id: str = Form(...), mensaje: str = Form(""), archivo: UploadFile | None = File(None)) -> dict:
    return {
        "session_id": session_id, "run_id": "mock", "tipo": "caso", "latencia_ms": 0,
        "respuesta": "(mock) El caso no procede: incumple el límite de endeudamiento.",
        "confianza": "media", "citas": [], "advertencias": [],
        "dictamen": {
            "resumen_caso": "Solicitud de crédito de consumo por S/ 70,000 aprobada por gerente de agencia.",
            "hechos": [{"dato": "Ingreso neto mensual", "valor": "S/ 6,000"}],
            "evaluaciones": [{
                "regla": "Endeudamiento máximo 35% del ingreso neto", "doc_id": "SINT-02",
                "nombre_norma": "Política de Crédito de Consumo", "articulo": "5", "version": "2",
                "estado": "vigente", "cita": "no podrá superar el 35% de su ingreso neto mensual",
                "resultado": "no_cumple", "explicacion": "(900 + 2,150) / 6,000 = 50.8% > 35%",
            }],
            "calculos": [{"descripcion": "Ratio de endeudamiento", "expresion": "(900+2150)/6000", "resultado": 0.508}],
            "conflictos": ["SINT-02 Art. 8 (S/ 50,000) contradice SINT-03 Art. 12 (S/ 80,000)"],
            "vacios": [],
            "conclusion": "no_procede",
            "acciones": ["Rechazar o reestructurar el monto", "Escalar el conflicto de autonomías a Cumplimiento"],
        },
    }


@router.get("/chat/ejemplos")
def ejemplos() -> list[dict]:
    return [{"id": "CASO-01", "titulo": "Crédito de consumo S/ 70,000 (mock)", "texto": "..."}]


@router.get("/chat/{session_id}")
def historial(session_id: str) -> list[dict]:
    return []
