# Hack AI Agents — esqueleto

Esqueleto genérico de un sistema multi-agente (FastAPI + DeepSeek) para el hackathon
"Hack AI Agents Impact" (NTT DATA x Sundai LATAM). Se adapta al sector asignado
(Banca, Minería o Manufactura) el día del evento.

## Correr en local

```bash
cp .env.example .env        # y completa DEEPSEEK_API_KEY
docker compose up --build
curl http://localhost:8000/health
```

Sin Docker:

```bash
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

> README en construcción: problema, solución, arquitectura y guías se completan en la etapa 8.
