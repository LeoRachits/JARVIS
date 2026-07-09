"""Servidor WebSocket local que publica eventos de estado para o HUD (SPEC-03)."""
from __future__ import annotations

import asyncio
import json
import logging
import threading

import websockets

logger = logging.getLogger("jarvis.desktop.hud_bridge")


class HudBridge:
    """Publica eventos em ws://127.0.0.1:{port} para o HUD consumir.

    Eventos enviados:
      {"type":"state",      "value":"idle|listening|thinking|speaking|error"}
      {"type":"level",      "value":0.0..1.0}
      {"type":"transcript", "text":"..."}
      {"type":"delta",      "text":"..."}
    """

    def __init__(self, port: int = 8765) -> None:
        self._port = port
        self._clients: set = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        """Inicia servidor WS em thread daemon. Retorna só quando estiver ouvindo."""
        ready = threading.Event()
        self._thread = threading.Thread(
            target=self._run, args=(ready,), daemon=True, name="hud-ws"
        )
        self._thread.start()
        if not ready.wait(timeout=5.0):
            logger.warning("HudBridge demorou para iniciar — seguindo mesmo assim")
        else:
            logger.info("HudBridge ouvindo em ws://127.0.0.1:%d", self._port)

    def broadcast(self, event: dict) -> None:
        """Thread-safe: enfileira evento para todos os clientes HUD conectados."""
        if self._loop is None or self._loop.is_closed():
            return
        asyncio.run_coroutine_threadsafe(self._send_all(event), self._loop)

    # ------------------------------------------------------------------ #
    # Internals (rodam no loop async da thread daemon)
    # ------------------------------------------------------------------ #
    def _run(self, ready: threading.Event) -> None:
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._serve(ready))
        except Exception:
            logger.exception("Erro fatal no loop do HudBridge")

    async def _serve(self, ready: threading.Event) -> None:
        try:
            async with websockets.serve(self._handler, "127.0.0.1", self._port):
                ready.set()
                await asyncio.Future()  # roda para sempre
        except OSError as exc:
            if exc.errno in (10048, 98):  # EADDRINUSE (Windows / Linux)
                logger.warning(
                    "Porta %d já em uso — HUD não vai conectar; "
                    "feche instâncias anteriores do Jarvis ou mude HUD_PORT no voice.env.",
                    self._port,
                )
                ready.set()  # não bloqueia start() mesmo sem servidor WS
            else:
                raise

    async def _handler(self, websocket) -> None:
        self._clients.add(websocket)
        logger.debug("HUD conectado — %d cliente(s)", len(self._clients))
        try:
            await websocket.wait_closed()
        finally:
            self._clients.discard(websocket)
            logger.debug("HUD desconectado — %d cliente(s)", len(self._clients))

    async def _send_all(self, event: dict) -> None:
        if not self._clients:
            return
        msg = json.dumps(event, ensure_ascii=False)
        dead: set = set()
        for ws in set(self._clients):
            try:
                await ws.send(msg)
            except Exception:
                dead.add(ws)
        self._clients -= dead
