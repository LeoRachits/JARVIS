"""Configuração central do Jarvis, carregada de variáveis de ambiente."""
from __future__ import annotations

import os
from dataclasses import dataclass
from dotenv import load_dotenv

load_dotenv()


def _require(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise RuntimeError(
            f"Variável de ambiente obrigatória ausente: {key}. "
            f"Copie .env.example para .env e preencha."
        )
    return value


@dataclass(frozen=True)
class Settings:
    anthropic_api_key: str
    model: str
    max_tokens: int
    jarvis_name: str
    user_name: str
    db_path: str
    host: str
    port: int
    api_token: str
    telegram_token: str
    telegram_allowed_user_id: int  # 0 = aceita qualquer um (NÃO recomendado)
    web_search_max_uses: int
    request_timeout: float
    max_retries: int


def load_settings() -> Settings:
    return Settings(
        anthropic_api_key=_require("ANTHROPIC_API_KEY"),
        model=os.getenv("JARVIS_MODEL", "claude-sonnet-4-6"),
        max_tokens=int(os.getenv("JARVIS_MAX_TOKENS", "1500")),
        jarvis_name=os.getenv("JARVIS_NAME", "Jarvis"),
        user_name=os.getenv("USER_NAME", "Senhor"),
        db_path=os.getenv("JARVIS_DB_PATH", "jarvis_memory.db"),
        host=os.getenv("JARVIS_HOST", "0.0.0.0"),
        port=int(os.getenv("JARVIS_PORT", "8787")),
        api_token=os.getenv("JARVIS_API_TOKEN", ""),
        telegram_token=os.getenv("TELEGRAM_TOKEN", ""),
        telegram_allowed_user_id=int(os.getenv("TELEGRAM_ALLOWED_USER_ID", "0")),
        web_search_max_uses=int(os.getenv("WEB_SEARCH_MAX_USES", "5")),
        request_timeout=float(os.getenv("JARVIS_REQUEST_TIMEOUT", "60")),
        max_retries=int(os.getenv("JARVIS_MAX_RETRIES", "2")),
    )
