"""Punto de entrada FastAPI."""
import logging
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse

from app.api import router as api_router
from app.config import get_settings
from app.logging_config import setup_logging

settings = get_settings()
setup_logging(settings.log_level)
log = logging.getLogger("app")


@asynccontextmanager
async def lifespan(_: FastAPI):
    log.info("Arrancando %s | modelo=%s", settings.app_name, settings.deepseek_model)
    if not settings.deepseek_api_key:
        log.warning("DEEPSEEK_API_KEY no está configurada")
    yield


app = FastAPI(title=settings.app_name, lifespan=lifespan)
app.include_router(api_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "model": settings.deepseek_model}


INDEX = Path(__file__).resolve().parent / "static" / "index.html"


@app.get("/", include_in_schema=False)
def index() -> FileResponse:
    return FileResponse(INDEX)
