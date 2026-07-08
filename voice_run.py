"""Liga o Jarvis de voz em segundo plano. O HUD abre ao dizer a palavra de ativação.

Uso:  python voice_run.py   (ou pythonw voice_run.py, sem janela, no auto-início)
"""
from __future__ import annotations

import logging
import pathlib
import sys
import webbrowser

from voice.assistant import VoiceAssistant
from voice.brain_client import BrainClient
from voice.config import load_voice_settings
from voice.hud_bridge import HudBridge
from voice.recorder import Recorder
from voice.stt import STT
from voice.tts import make_tts
from voice.wakeword import WakeWord


def _setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )


def _make_hud_opener(log: logging.Logger):
    """Devolve uma função que abre o jarvis_hud.html no navegador (chamada ao ativar)."""
    hud = pathlib.Path(__file__).resolve().parent / "jarvis_hud.html"

    def opener() -> None:
        if hud.is_file():
            webbrowser.open(hud.as_uri())
            log.info("HUD aberto: %s", hud.name)
        else:
            log.info("jarvis_hud.html não encontrado; seguindo sem HUD.")

    return opener


def main() -> int:
    try:
        settings = load_voice_settings()
    except RuntimeError as exc:
        print(f"[config] {exc}", file=sys.stderr)
        return 2

    _setup_logging(settings.log_level)
    log = logging.getLogger("jarvis.voice")

    try:
        hud = HudBridge()
        hud.start()

        wakeword = WakeWord(settings.wakeword_model, settings.wakeword_threshold, settings.mic_device)
        recorder = Recorder(
            aggressiveness=settings.vad_aggressiveness,
            silence_ms=settings.silence_ms,
            max_record_seconds=settings.max_record_seconds,
            start_timeout_seconds=settings.start_timeout_seconds,
            device=settings.mic_device,
        )
        stt = STT(settings.whisper_model, settings.whisper_device, settings.whisper_compute_type, settings.whisper_language)
        brain = BrainClient(
            base_url=settings.brain_url,
            api_token=settings.api_token,
            session_id=settings.session_id,
            timeout=settings.brain_timeout,
            max_retries=settings.brain_max_retries,
        )
        tts = make_tts(settings)
    except Exception as exc:  # noqa: BLE001
        log.exception("Falha ao inicializar a camada de voz: %s", exc)
        return 1

    assistant = VoiceAssistant(
        settings, wakeword, recorder, stt, brain, tts,
        hud=hud, hud_opener=_make_hud_opener(log),
    )
    try:
        assistant.run_forever()
    except KeyboardInterrupt:
        log.info("Encerrando. Até logo.")
        return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
