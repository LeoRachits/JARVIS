"""Detecção offline de wake word 'jarvis' via Vosk (PT-BR)."""
from __future__ import annotations

import json
import logging
import threading
from pathlib import Path
from typing import Callable

import sounddevice as sd
from vosk import KaldiRecognizer, Model, SetLogLevel

logger = logging.getLogger("jarvis.desktop.wake_word")

_SAMPLE_RATE = 16_000
_BLOCK_FRAMES = 4_000   # 4000 frames × 2 bytes/frame = 8000 bytes ≈ 0.25s
_GRAMMAR = '["jarvis", "[unk]"]'


class WakeWordDetector:
    """Escuta continuamente o microfone e dispara callback ao ouvir 'jarvis'.

    pause()/resume() cedem o microfone ao Listener sem fechar o stream.
    """

    def __init__(
        self,
        model_path: str = "models/vosk-model-small-pt-0.3",
        device: int | None = None,
        on_wake: Callable[[], None] | None = None,
    ) -> None:
        self._model_path = model_path
        self._device = device
        self._on_wake = on_wake
        self._running = False
        self._active = threading.Event()
        self._active.set()  # set = ativo; clear = pausado
        self._thread: threading.Thread | None = None
        self._model: Model | None = None

    def register_on_wake(self, callback: Callable[[], None]) -> None:
        self._on_wake = callback

    def start(self) -> None:
        """Carrega modelo Vosk e inicia thread de escuta.

        Levanta FileNotFoundError se o modelo não for encontrado.
        """
        p = Path(self._model_path)
        model_abs = p if p.is_absolute() else Path(__file__).parent / p
        if not model_abs.is_dir():
            msg = (
                f"Modelo Vosk não encontrado em '{model_abs}'.\n"
                "Baixe vosk-model-small-pt-0.3 em https://alphacephei.com/vosk/models\n"
                "e descompacte em jarvis-desktop/models/vosk-model-small-pt-0.3/."
            )
            logger.error(msg)
            raise FileNotFoundError(msg)

        SetLogLevel(-1)
        logger.info("Carregando modelo Vosk de '%s'...", model_abs)
        self._model = Model(str(model_abs))
        logger.info("WakeWordDetector pronto — escutando por 'jarvis'.")

        self._running = True
        self._thread = threading.Thread(
            target=self._run, daemon=True, name="wake-word"
        )
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        self._active.set()  # desbloqueia caso esteja pausado

    def pause(self) -> None:
        """Pausa o processamento (stream permanece aberto, buffers drenados)."""
        self._active.clear()

    def resume(self) -> None:
        """Retoma o processamento após pause()."""
        self._active.set()

    def _run(self) -> None:
        rec = KaldiRecognizer(self._model, _SAMPLE_RATE, _GRAMMAR)
        try:
            with sd.RawInputStream(
                samplerate=_SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=_BLOCK_FRAMES,
                device=self._device,
            ) as stream:
                while self._running:
                    data, _ = stream.read(_BLOCK_FRAMES)

                    if not self._active.is_set():
                        self._active.wait()
                        rec.Reset()  # descarta estado acumulado durante a pausa
                        continue

                    raw = bytes(data)
                    if rec.AcceptWaveform(raw):
                        text = json.loads(rec.Result()).get("text", "")
                    else:
                        text = json.loads(rec.PartialResult()).get("partial", "")

                    if "jarvis" in text.lower():
                        logger.info("Wake word detectada: %r", text)
                        rec.Reset()
                        if self._on_wake and self._running:
                            threading.Thread(
                                target=self._on_wake, daemon=True, name="wake-cb"
                            ).start()
        except Exception:
            logger.exception("Erro no loop do WakeWordDetector")
