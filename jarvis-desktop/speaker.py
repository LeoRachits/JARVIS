"""Fala a resposta do Jarvis em streaming de frases via TTS HTTP."""
from __future__ import annotations

import logging
import threading
from typing import Callable, Iterator

import httpx
import miniaudio
import numpy as np
import sounddevice as sd

logger = logging.getLogger("jarvis.desktop.speaker")

_SENTENCE_ENDS = frozenset(".!?…\n")
_MIN_PHRASE_LEN = 15    # frases muito curtas não valem uma chamada TTS
_LEVEL_BLOCK_S = 0.05   # intervalo de medição de RMS para o HUD (~50ms)


class Speaker:
    """Fala deltas de texto em streaming: acumula por frase, chama TTS, toca MP3.

    Modo streaming:
      - speak_stream(iter_texto) consome deltas, quebra em frases (. ! ? …)
        e toca cada frase assim que completa, enquanto o restante ainda chega.
      - Barge-in: interrupt() para o playback na próxima fronteira de bloco.
    """

    def __init__(
        self,
        brain_url: str,
        brain_token: str = "",
        on_level: Callable[[float], None] | None = None,
    ) -> None:
        self._url = brain_url.rstrip("/")
        self._headers: dict[str, str] = {}
        if brain_token:
            self._headers["Authorization"] = f"Bearer {brain_token}"
        self._on_level = on_level
        self._stop = threading.Event()

    # ------------------------------------------------------------------ #
    # API pública
    # ------------------------------------------------------------------ #
    def speak_stream(self, text_iter: Iterator[str]) -> None:
        """Consome deltas de texto e fala frase a frase em streaming."""
        self._stop.clear()
        buffer = ""
        for chunk in text_iter:
            if self._stop.is_set():
                break
            buffer += chunk
            while True:
                idx = self._find_sentence_end(buffer)
                if idx == -1:
                    break
                phrase = buffer[: idx + 1].strip()
                buffer = buffer[idx + 1 :]
                if len(phrase) >= _MIN_PHRASE_LEN:
                    self._speak_phrase(phrase)
                if self._stop.is_set():
                    return
        # Fala o restante que não terminou em pontuação
        if buffer.strip() and not self._stop.is_set():
            self._speak_phrase(buffer.strip())

    def speak_text(self, text: str) -> None:
        """Fala texto completo (avisos de erro, mensagens do sistema)."""
        self._stop.clear()
        self._speak_phrase(text)

    def interrupt(self) -> None:
        """Barge-in: para o playback na fronteira de bloco mais próxima."""
        self._stop.set()

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    @staticmethod
    def _find_sentence_end(text: str) -> int:
        for i, ch in enumerate(text):
            if ch in _SENTENCE_ENDS:
                return i
        return -1

    def _speak_phrase(self, text: str) -> None:
        if self._stop.is_set():
            return
        try:
            with httpx.Client(timeout=30.0) as client:
                resp = client.post(
                    f"{self._url}/speak",
                    json={"text": text},
                    headers=self._headers,
                )
                resp.raise_for_status()
                audio_bytes = resp.content
        except Exception:
            logger.exception("Falha no TTS para: %.60s", text)
            return
        try:
            self._play_mp3(audio_bytes)
        except Exception:
            logger.exception("Falha no playback de áudio")

    def _play_mp3(self, audio_bytes: bytes) -> None:
        """Decodifica MP3 com miniaudio e toca com sounddevice, emitindo RMS ao HUD."""
        decoded = miniaudio.decode(
            audio_bytes,
            output_format=miniaudio.SampleFormat.FLOAT32,
            nchannels=1,
        )
        data = np.frombuffer(decoded.samples, dtype=np.float32)
        samplerate = decoded.sample_rate
        block_size = max(1, int(samplerate * _LEVEL_BLOCK_S))
        idx = 0
        with sd.OutputStream(
            samplerate=samplerate, channels=1, dtype="float32"
        ) as stream:
            while idx < len(data) and not self._stop.is_set():
                chunk = data[idx : idx + block_size]
                stream.write(chunk)
                if self._on_level:
                    rms = float(np.sqrt(np.mean(chunk ** 2)))
                    self._on_level(min(rms * 10.0, 1.0))
                idx += block_size
        if self._on_level:
            self._on_level(0.0)
