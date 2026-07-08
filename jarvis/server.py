"""API HTTP do Jarvis — é por aqui que o PC e o celular conversam com o cérebro.

Endpoints:
- GET  /health       — checagem de vida.
- POST /chat         — resposta completa de uma vez (Telegram, reserva).
- POST /chat/stream  — resposta em streaming (SSE) para a voz começar a falar antes.
- POST /reset        — limpa a memória de uma sessão.
"""
from __future__ import annotations

import json
import logging
from typing import Iterator

from fastapi import FastAPI, Header, HTTPException, Response
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from .tts import build_tts

from .brain import Brain
from .config import load_settings

settings = load_settings()
brain = Brain(settings)
app = FastAPI(title="Jarvis Brain", version="1.1.0")
log = logging.getLogger("jarvis.server")
_tts = None


def _get_tts():
    global _tts
    if _tts is None:
        _tts = build_tts(settings)
    return _tts


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


def _sse_events(session_id: str, message: str) -> Iterator[str]:
    """Converte os dicts do chat_stream em eventos SSE nomeados."""
    # TODO: heartbeat keep-alive (": \n\n" periódico) — implementar em SPEC-03
    try:
        for ev in brain.chat_stream(session_id, message):
            yield f"event: {ev['type']}\ndata: {json.dumps(ev, ensure_ascii=False)}\n\n"
    except Exception as exc:
        payload = json.dumps({"type": "error", "message": str(exc)}, ensure_ascii=False)
        yield f"event: error\ndata: {payload}\n\n"


@app.post("/chat/stream")
def chat_stream(
    request: ChatRequest,
    authorization: str | None = Header(default=None),
) -> StreamingResponse:
    _check_auth(authorization)
    return StreamingResponse(
        _sse_events(request.session_id, request.message),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


class SpeakRequest(BaseModel):
    text: str = Field(..., min_length=1)


@app.post("/speak")
def speak(
    request: SpeakRequest,
    authorization: str | None = Header(default=None),
) -> Response:
    _check_auth(authorization)
    try:
        audio = _get_tts().synthesize(request.text)
    except Exception as exc:
        log.error("Falha na síntese de voz: %s", exc)
        raise HTTPException(status_code=500, detail="Falha ao gerar a fala.")
    return Response(content=audio, media_type="audio/mpeg")


@app.post("/reset")
def reset(
    session_id: str = "default",
    authorization: str | None = Header(default=None),
) -> dict[str, str]:
    _check_auth(authorization)
    brain.reset(session_id)
    return {"status": "memória limpa", "session_id": session_id}
