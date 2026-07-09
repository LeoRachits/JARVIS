"""Orquestrador do cliente de voz Jarvis Desktop.

Máquina de estados:
  idle ──(wake word 'jarvis')──► listening ──(texto)──► thinking/speaking ──► followup
                                           └─(silêncio)──► idle             │
                                                            (barge-in wake)──┘► listening
                                                            (silêncio 8s)──────► idle
"""
from __future__ import annotations

import logging
import sys
import threading
from logging.handlers import RotatingFileHandler
from pathlib import Path

import numpy as np
import sounddevice as sd

sys.path.insert(0, str(Path(__file__).parent))

from brain_client import BrainClient, BrainConnectionError
from config import load_config
from hud_bridge import HudBridge
from listener import Listener
from speaker import Speaker
from wake_word import WakeWordDetector

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

        self._hud = HudBridge(port=self._cfg.hud_port)
        self._brain = BrainClient(self._cfg.brain_url, self._cfg.brain_token)
        self._listener = Listener(device=self._cfg.audio_device)
        self._speaker = Speaker(
            brain_url=self._cfg.brain_url,
            brain_token=self._cfg.brain_token,
            on_level=lambda lvl: self._hud.broadcast({"type": "level", "value": lvl}),
        )
        self._wake_event = threading.Event()
        self._wake_detector = WakeWordDetector(
            model_path=self._cfg.wake_model_path,
            device=self._cfg.audio_device,
            on_wake=self._on_wake,
        )

    def run(self) -> None:
        self._hud.start()
        self._wake_detector.start()
        self._set_state("idle")
        logger.info(
            "Jarvis Desktop pronto. Diga 'Jarvis' para ativar "
            "(brain=%s, followup=%gs).",
            self._cfg.brain_url,
            self._cfg.followup_window_sec,
        )

        while True:
            try:
                if self._state == "idle":
                    self._await_activation()
                elif self._state == "listening":
                    self._handle_listening()
                elif self._state == "followup":
                    self._handle_followup()
            except KeyboardInterrupt:
                logger.info("Encerrando por interrupção do teclado.")
                break
            except Exception:
                logger.exception("Erro no loop principal — reiniciando em idle")
                self._speaker.interrupt()
                self._set_state("idle")

    def _await_activation(self) -> None:
        """Bloqueia até wake word 'jarvis', toca chime, vai para listening."""
        self._wake_event.wait()
        self._wake_event.clear()
        self._play_chime()
        self._set_state("listening")

    def _handle_listening(self) -> None:
        """Pausa detector, grava + transcreve, retoma detector."""
        self._wake_detector.pause()
        try:
            text = self._listener.listen_and_transcribe()
        finally:
            self._wake_detector.resume()

        if not text:
            self._set_state("idle")
            return

        self._hud.broadcast({"type": "transcript", "text": text})
        self._run_thinking(text)

    def _handle_followup(self) -> None:
        """Escuta por até FOLLOWUP_WINDOW_SEC sem exigir nova wake word."""
        logger.info(
            "Escuta de acompanhamento (até %gs)...", self._cfg.followup_window_sec
        )
        self._wake_detector.pause()
        try:
            text = self._listener.listen_and_transcribe(
                pre_speech_sec=self._cfg.followup_window_sec
            )
        finally:
            self._wake_detector.resume()

        if not text:
            logger.info("Silêncio no follow-up — voltando a idle.")
            self._set_state("idle")
            return

        self._hud.broadcast({"type": "transcript", "text": text})
        self._run_thinking(text)

    def _run_thinking(self, text: str) -> None:
        """Consome stream do cérebro, fala a resposta, detecta barge-in por wake word."""
        self._set_state("thinking")
        self._wake_event.clear()
        first_delta = [True]

        def delta_gen():
            for ev in self._brain.stream_chat(text, session_id="desktop"):
                self._hud.broadcast(ev)
                ev_type = ev.get("type")
                if ev_type == "delta":
                    if first_delta[0]:
                        self._set_state("speaking")
                        first_delta[0] = False
                    yield ev["text"]
                elif ev_type == "error":
                    logger.error("Erro do cérebro: %s", ev.get("message"))
                    return
                elif ev_type == "done":
                    return

        try:
            self._speaker.speak_stream(delta_gen())
        except BrainConnectionError:
            logger.error("Sem conexão com o cérebro")
            self._speaker.speak_text(
                "Estou sem conexão com meu cérebro agora. Tente em instantes."
            )
            self._set_state("idle")
            return
        except Exception:
            logger.exception("Erro durante thinking/speaking")
            self._set_state("idle")
            return

        if self._wake_event.is_set():
            # Barge-in por wake word detectada durante speaking
            self._wake_event.clear()
            logger.info("Barge-in por wake word — voltando a listening")
            self._set_state("listening")
        else:
            self._set_state("followup")

    def _on_wake(self) -> None:
        """Callback da thread do WakeWordDetector — não pode bloquear."""
        if self._state == "speaking":
            logger.info("Barge-in detectado por wake word: interrompendo fala")
            self._speaker.interrupt()
            self._wake_event.set()
        elif self._state == "idle":
            self._wake_event.set()
        # listening / thinking / followup: ignorar

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
