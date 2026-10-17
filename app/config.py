"""Configuración central leída desde variables de entorno (.env)."""
from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Hack AI Agents"
    sector: str = "generico"  # generico | banca | mineria | manufactura
    log_level: str = "INFO"

    deepseek_api_key: str = ""
    deepseek_model: str = "deepseek-flash"
    deepseek_base_url: str = "https://api.deepseek.com"

    # Comportamiento del cliente LLM
    llm_timeout: float = 60.0          # segundos por request
    llm_max_retries: int = 3           # reintentos ante errores transitorios
    llm_thinking: bool = False         # modo thinking por defecto (configurable por agente)
    llm_reasoning_effort: str = "high"  # low | high | max (solo aplica con thinking)


@lru_cache
def get_settings() -> Settings:
    return Settings()
