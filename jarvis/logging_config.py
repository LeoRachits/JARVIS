"""Configuração de log estruturado do Jarvis.

Chame setup_logging() uma vez, no início de cada ponto de entrada
(cli.py, server.py, telegram_bot.py). O log vai para o console e, se
JARVIS_LOG_FILE estiver definido, também para um arquivo com rotação.
Nunca logamos segredos (chave de API, tokens).
"""
from __future__ import annotations

import logging
import os
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

_CONFIGURED = False

_FORMAT = "%(asctime)s | %(levelname)-7s | %(name)s | %(message)s"
_DATEFMT = "%Y-%m-%d %H:%M:%S"


def setup_logging() -> None:
    """Configura o logging global uma única vez (idempotente)."""
    global _CONFIGURED
    if _CONFIGURED:
        return

    load_dotenv()  # garante que JARVIS_LOG_* do .env estejam disponíveis

    level_name = os.getenv("JARVIS_LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    root = logging.getLogger()
    root.setLevel(level)

    formatter = logging.Formatter(_FORMAT, datefmt=_DATEFMT)

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    root.addHandler(console)

    log_file = os.getenv("JARVIS_LOG_FILE", "").strip()
    if log_file:
        file_handler = RotatingFileHandler(
            log_file, maxBytes=2_000_000, backupCount=5, encoding="utf-8"
        )
        file_handler.setFormatter(formatter)
        root.addHandler(file_handler)

    # Bibliotecas barulhentas ficam num nível mais alto.
    for noisy in ("httpx", "httpcore", "anthropic", "telegram", "urllib3"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True
    logging.getLogger("jarvis").info("Logging configurado (nível=%s).", level_name)
