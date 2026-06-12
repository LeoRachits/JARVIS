"""API HTTP do Jarvis — é por aqui que o PC e o celular conversam com o cérebro."""
from __future__ import annotations

import logging

from fastapi import FastAPI, Header, HTTPException
from pydantic import BaseModel, Field

from .brain import Brain
from .config import load_settings
from .logging_config import setup_logging

setup_logging()
logger = logging.getLogger(__name__)

settings = load_settings()
brain = Brain(settings)
app = FastAPI(title="Jarvis Brain", version="1.0.0")


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    session_id: str = Field(default="default")


class ChatResponse(BaseModel):
    reply: str


def _check_auth(authorization: str | None) -> None:
    """Protege o servidor com um token. Sem isso, qualquer um na rede acessa."""
    if not settings.api_token:
        return  # token não configurado — liberado (ok só para testes locais)
    expected = f"Bearer {settings.api_token}"
    if authorization != expected:
        logger.warning("Tentativa de acesso sem token válido.")
        raise HTTPException(status_code=401, detail="Não autorizado.")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "jarvis": settings.jarvis_name}


@app.post("/chat", response_model=ChatResponse)
def chat(
    request: ChatRequest,
    authorization: str | None = Header(default=None),
) -> ChatResponse:
    _check_auth(authorization)
    reply = brain.chat(request.session_id, request.message)
    return ChatResponse(reply=reply)


@app.post("/reset")
def reset(
    session_id: str = "default",
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    _check_auth(authorization)
    brain.reset(session_id)
    return {"status": "memória limpa", "session_id": session_id}
