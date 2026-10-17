"""Agentes del caso. Cambiar roles/tools aquí al adaptar al sector."""
from app.agents.agent import Agent

asistente = Agent(
    name="asistente",
    role=(
        "Eres un agente operativo. Analizas solicitudes sobre entidades, consultas sus datos "
        "y, si corresponde, creas órdenes. Al final entrega un resumen claro de lo realizado."
    ),
    tools=["consultar_entidad", "crear_orden"],
    thinking=None,  # None = global (OFF). Poner True para activar thinking solo en este agente.
)

# Caso de ejemplo de punta a punta (usado por la API y scripts/run_example.py)
CASO_EJEMPLO = (
    "Revisa las entidades ENT-001 y ENT-002. A cada una que esté activa créale una orden de 3000 "
    "por 'mantenimiento preventivo'. Luego resume qué se hizo."
)
