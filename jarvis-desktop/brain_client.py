"""Consome o endpoint /chat/stream do cérebro via SSE com retry e backoff."""
from __future__ import annotations

import json
import logging
import time
from typing import Iterator

import httpx

logger = logging.getLogger("jarvis.desktop.brain_client")

_RETRY_DELAYS = (2, 5, 10, 30)   # segundos entre tentativas (4 retries máx)


class BrainConnectionError(RuntimeError):
    """Impossível alcançar o cérebro após todas as tentativas de reconexão."""


class BrainClient:
    def __init__(self, brain_url: str, brain_token: str = "") -> None:
        self._url = brain_url.rstrip("/")
        self._headers: dict[str, str] = {}
        if brain_token:
            self._headers["Authorization"] = f"Bearer {brain_token}"

    def stream_chat(self, message: str, session_id: str = "desktop") -> Iterator[dict]:
        """POST /chat/stream, parseia SSE e faz yield de cada evento decodificado.

        Retry com backoff (2s→5s→10s→30s) em falha de conexão.
        Levanta BrainConnectionError se todas as tentativas esgotarem.
        """
        payload = {"message": message, "session_id": session_id}
        delays = (0,) + _RETRY_DELAYS
        last_exc: Exception | None = None

        for attempt, delay in enumerate(delays, start=1):
            if delay > 0:
                logger.warning(
                    "stream_chat — tentativa %d/%d, aguardando %ds...",
                    attempt, len(delays), delay,
                )
                time.sleep(delay)
            try:
                yield from self._do_stream(payload)
                return
            except httpx.ConnectError as exc:
                logger.error(
                    "Falha de conexão (tentativa %d/%d): %s", attempt, len(delays), exc
                )
                last_exc = exc
            except httpx.HTTPStatusError as exc:
                logger.error("HTTP %d do cérebro: %s", exc.response.status_code, exc)
                last_exc = exc
                break   # erros HTTP não fazem retry
            except Exception as exc:
                logger.exception("Erro inesperado no stream (tentativa %d)", attempt)
                last_exc = exc
                break

        raise BrainConnectionError(
            f"Não foi possível conectar ao cérebro em {self._url} "
            f"após {len(delays)} tentativa(s)."
        ) from last_exc

    def _do_stream(self, payload: dict) -> Iterator[dict]:
        with httpx.Client(timeout=120.0) as client:
            with client.stream(
                "POST",
                f"{self._url}/chat/stream",
                json=payload,
                headers={**self._headers, "Accept": "text/event-stream"},
            ) as response:
                response.raise_for_status()
                for line in response.iter_lines():
                    if not line.startswith("data:"):
                        continue
                    raw = line[len("data:"):].strip()
                    if not raw:
                        continue
                    try:
                        yield json.loads(raw)
                    except json.JSONDecodeError:
                        logger.warning("Linha SSE com JSON inválido ignorada: %s", raw)
