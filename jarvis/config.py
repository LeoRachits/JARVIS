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


def _bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "sim", "on"}


@dataclass(frozen=True)
class Settings:
    # Chaves dos provedores
    anthropic_api_key: str          # usada pelo Claude e pela busca na web
    deepseek_api_key: str           # usada pelo DeepSeek (vazio = DeepSeek desligado)
    deepseek_base_url: str

    # Modelos
    default_model: str              # modelo PADRÃO de toda conversa (DeepSeek)
    claude_model: str               # modelo "premium" ao trocar por comando ("usa o Claude")
    search_model: str               # modelo barato que faz a busca na web emprestada
    max_tokens: int

    # Busca na web
    web_search_max_uses: int
    enable_web_search: bool         # liga/desliga a pesquisa por completo

    # Personalidade
    jarvis_name: str
    user_name: str

    # Memória
    db_path: str

    # Servidor HTTP
    host: str
    port: int
    api_token: str

    # Telegram
    telegram_token: str
    telegram_allowed_user_id: int   # 0 = aceita qualquer um (NÃO recomendado)

    # Robustez (rodar 24h)
    request_timeout: float
    max_retries: int
    tool_loop_limit: int


def load_settings() -> Settings:
    return Settings(
        # --- Provedores ---
        anthropic_api_key=_require("ANTHROPIC_API_KEY"),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", ""),
        deepseek_base_url=os.getenv(
            "DEEPSEEK_BASE_URL", "https://api.deepseek.com/anthropic"
        ),
        # --- Modelos ---
        # Padrão = DeepSeek (barato). Troca pro Claude por comando de voz.
        default_model=os.getenv("JARVIS_MODEL", "deepseek-v4-flash"),
        claude_model=os.getenv("JARVIS_CLAUDE_MODEL", "claude-sonnet-4-6"),
        # Busca emprestada: Haiku é barato/rápido e já faz a síntese da pesquisa.
        search_model=os.getenv("JARVIS_SEARCH_MODEL", "claude-haiku-4-5"),
        max_tokens=int(os.getenv("JARVIS_MAX_TOKENS", "1500")),
        # --- Busca na web ---
        web_search_max_uses=int(os.getenv("WEB_SEARCH_MAX_USES", "5")),
        enable_web_search=_bool("ENABLE_WEB_SEARCH", True),
        # --- Personalidade ---
        jarvis_name=os.getenv("JARVIS_NAME", "Jarvis"),
        user_name=os.getenv("USER_NAME", "Senhor"),
        # --- Memória ---
        db_path=os.getenv("JARVIS_DB_PATH", "jarvis_memory.db"),
        # --- Servidor ---
        host=os.getenv("JARVIS_HOST", "0.0.0.0"),
        port=int(os.getenv("JARVIS_PORT", "8787")),
        api_token=os.getenv("JARVIS_API_TOKEN", ""),
        # --- Telegram ---
        telegram_token=os.getenv("TELEGRAM_TOKEN", ""),
        telegram_allowed_user_id=int(os.getenv("TELEGRAM_ALLOWED_USER_ID", "0")),
        # --- Robustez ---
        request_timeout=float(os.getenv("JARVIS_REQUEST_TIMEOUT", "60")),
        max_retries=int(os.getenv("JARVIS_MAX_RETRIES", "3")),
        tool_loop_limit=int(os.getenv("JARVIS_TOOL_LOOP_LIMIT", "6")),
    )
