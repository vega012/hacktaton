"""Punto de entrada FastAPI."""
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

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


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "app": settings.app_name, "model": settings.deepseek_model}
