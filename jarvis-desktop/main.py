"""Orquestrador do cliente de voz Jarvis Desktop.

Máquina de estados:
  idle ──(palma dupla)──► listening ──(transcrição)──► thinking ──► speaking ──► idle
                                    └─(silêncio)──► idle               ▲
                                                                (barge-in)──► listening
"""
# ── Mythus Solutions ── Jarvis Desktop ── jarvis-desktop/main.py ─────────────
from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

import numpy as np
import sounddevice as sd

# Garante que imports locais funcionem independentemente do cwd
sys.path.insert(0, str(Path(__file__).parent))

from brain_client import BrainClient, BrainConnectionError  # noqa: E402
from clap_detector import ClapDetector                       # noqa: E402
from config import load_config                               # noqa: E402
from hud_bridge import HudBridge                             # noqa: E402
from listener import Listener                                # noqa: E402
from speaker import Speaker                                  # noqa: E402

logger = logging.getLogger("jarvis.desktop.main")


def _setup_logging() -> None:
    log_dir = Path(__file__).parent / "logs"
    log_dir.mkdir(exist_ok=True)
    fmt = "%(asctime)s %(levelname)-8s %(name)s — %(message)s"
    handlers: list[logging.Handler] = [
        logging.StreamHandler(),
        RotatingFileHandler(
            log_dir / "jarvis-desktop.log",
            maxBytes=5_000_000,
            backupCount=3,
            encoding="utf-8",
        ),
    ]
    logging.basicConfig(level=logging.INFO, format=fmt, handlers=handlers, force=True)


class JarvisDesktop:
    """Máquina de estados principal do cliente de voz."""

    def __init__(self) -> None:
        self._cfg = load_config()
        self._state = "idle"

        self._hud = HudBridge(port=self._cfg.ws_port)
        self._brain = BrainClient(self._cfg.brain_url, self._cfg.brain_token)
        self._listener = Listener(device=self._cfg.audio_device)
        self._speaker = Speaker(
            brain_url=self._cfg.brain_url,
            brain_token=self._cfg.brain_token,
            on_level=lambda lvl: self._hud.broadcast({"type": "level", "value": lvl}),
        )
        self._clap_event = threading.Event()
        self._clap_detector = ClapDetector(
            sensitivity=self._cfg.clap_sensitivity,
            device=self._cfg.audio_device,
            on_double_clap=self._on_double_clap,
        )

    # ------------------------------------------------------------------ #
    # Loop principal
    # ------------------------------------------------------------------ #
    def run(self) -> None:
        self._hud.start()
        self._clap_detector.start()
        self._set_state("idle")
        logger.info(
            "Jarvis Desktop pronto. Aguardando palma dupla "
            "(sensitivity=%.1f, brain=%s).",
            self._cfg.clap_sensitivity,
            self._cfg.brain_url,
        )

        while True:
            try:
                if self._state == "idle":
                    self._await_activation()
                elif self._state == "listening":
                    self._handle_listening()
                # thinking/speaking são sub-estados gerenciados por _handle_thinking
            except KeyboardInterrupt:
                logger.info("Encerrando por interrupção do teclado.")
                break
            except Exception:
                logger.exception("Erro no loop principal — reiniciando em idle")
                self._speaker.interrupt()
                self._set_state("idle")

    # ------------------------------------------------------------------ #
    # Handlers de estado
    # ------------------------------------------------------------------ #
    def _await_activation(self) -> None:
        """Bloqueia até palma dupla, toca chime e transiciona para listening."""
        self._clap_event.wait()
        self._clap_event.clear()
        self._play_chime()
        self._set_state("listening")

    def _handle_listening(self) -> None:
        """Grava + transcreve. Silêncio → idle. Texto → thinking/speaking → idle."""
        text = self._listener.listen_and_transcribe()
        if not text:
            self._set_state("idle")
            return

        self._hud.broadcast({"type": "transcript", "text": text})

        try:
            self._handle_thinking(text)
        except BrainConnectionError:
            logger.error("Sem conexão com o cérebro")
            self._speaker.speak_text(
                "Estou sem conexão com meu cérebro agora. Tente em instantes."
            )
            self._set_state("idle")
        except Exception:
            logger.exception("Erro durante thinking/speaking")
            self._set_state("idle")

    def _handle_thinking(self, text: str) -> None:
        """Consome stream do cérebro, fala a resposta e detecta barge-in."""
        self._set_state("thinking")
        self._clap_event.clear()
        first_delta = [True]

        def delta_gen():
            for ev in self._brain.stream_chat(text, session_id="desktop"):
                self._hud.broadcast(ev)
                ev_type = ev.get("type")
                if ev_type == "delta":
                    if first_delta[0]:
                        # Primeiro texto chegou: transiciona para speaking
                        self._set_state("speaking")
                        self._clap_detector.set_barge_in_mode(True)
                        first_delta[0] = False
                    yield ev["text"]
                elif ev_type == "error":
                    logger.error("Erro do cérebro: %s", ev.get("message"))
                    return
                elif ev_type == "done":
                    return

        try:
            self._speaker.speak_stream(delta_gen())
        finally:
            self._clap_detector.set_barge_in_mode(False)

        # Barge-in: clap_event foi setado por _on_double_clap durante speaking
        if self._clap_event.is_set():
            self._clap_event.clear()
            logger.info("Barge-in: voltando a ouvir")
            self._set_state("listening")
        else:
            self._set_state("idle")

    # ------------------------------------------------------------------ #
    # Callbacks e utilitários
    # ------------------------------------------------------------------ #
    def _on_double_clap(self) -> None:
        """Chamado pela thread do ClapDetector — não pode bloquear."""
        if self._state == "speaking":
            logger.info("Barge-in detectado: interrompendo fala")
            self._speaker.interrupt()
            self._clap_event.set()
        elif self._state == "idle":
            self._clap_event.set()
        # Em listening/thinking: ignorar para não interromper transcrição em andamento

    def _set_state(self, state: str) -> None:
        self._state = state
        self._hud.broadcast({"type": "state", "value": state})
        logger.info("Estado → %s", state)

    def _play_chime(self) -> None:
        """Tom de ativação: 880Hz por 150ms."""
        try:
            sr = self._cfg.sample_rate
            t = np.linspace(0, 0.15, int(sr * 0.15), endpoint=False)
            beep = (0.25 * np.sin(2 * np.pi * 880 * t)).astype(np.float32)
            sd.play(beep, samplerate=sr)
            sd.wait()
        except Exception:
            logger.warning("Falha ao tocar chime — continuando sem som de ativação")


def main() -> None:
    _setup_logging()
    JarvisDesktop().run()


if __name__ == "__main__":
    main()
