"""Gravação do microfone e transcrição com faster-whisper (small, int8, PT-BR)."""
# ── Mythus Solutions ── Jarvis Desktop ── jarvis-desktop/listener.py ─────────
from __future__ import annotations

import logging

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

logger = logging.getLogger("jarvis.desktop.listener")

_SAMPLE_RATE = 16_000
_BLOCK_MS = 32
_BLOCK_SIZE = int(_SAMPLE_RATE * _BLOCK_MS / 1000)   # 512 amostras
_SILENCE_RMS = 0.003                                   # ~−50dBFS
_SILENCE_BLOCKS = int(1.2 * 1000 / _BLOCK_MS)         # 1.2s de silêncio = encerra
_MAX_BLOCKS = int(15 * 1000 / _BLOCK_MS)               # 15s máximo
_MIN_TEXT_LEN = 3                                      # transcrições triviais descartadas


class Listener:
    """Grava do microfone até silêncio ou 15s e transcreve em PT com Whisper."""

    def __init__(self, device: int | None = None) -> None:
        self._device = device
        logger.info(
            "Carregando Whisper small (int8, CPU) — pode demorar no 1.º boot..."
        )
        self._model = WhisperModel("small", device="cpu", compute_type="int8")
        logger.info("Whisper pronto.")

    def listen_and_transcribe(self) -> str | None:
        """Grava até silêncio ou 15s, transcreve em PT-BR. Retorna texto ou None."""
        logger.info("Ouvindo...")
        audio = self._record()
        if audio is None or len(audio) < _SAMPLE_RATE // 2:
            logger.info("Nenhum áudio significativo capturado.")
            return None

        duration_s = len(audio) / _SAMPLE_RATE
        logger.info("Transcrevendo %.1fs de áudio...", duration_s)
        try:
            segments, _ = self._model.transcribe(
                audio,
                language="pt",
                beam_size=5,
                vad_filter=True,
            )
            text = " ".join(s.text for s in segments).strip()
        except Exception:
            logger.exception("Falha na transcrição Whisper")
            return None

        if len(text) < _MIN_TEXT_LEN:
            logger.info("Transcrição vazia ou muito curta: %r", text)
            return None

        logger.info("Transcrito: %r", text)
        return text

    def _record(self) -> np.ndarray | None:
        """Grava blocos de 32ms com VAD simples até silêncio ou 15s."""
        chunks: list[np.ndarray] = []
        silent_count = 0

        try:
            with sd.InputStream(
                samplerate=_SAMPLE_RATE,
                channels=1,
                dtype="float32",
                blocksize=_BLOCK_SIZE,
                device=self._device,
            ) as stream:
                for _ in range(_MAX_BLOCKS):
                    block, _ = stream.read(_BLOCK_SIZE)
                    chunks.append(block.copy())
                    rms = float(np.sqrt(np.mean(block ** 2)))
                    if rms < _SILENCE_RMS:
                        silent_count += 1
                    else:
                        silent_count = 0
                    if silent_count >= _SILENCE_BLOCKS:
                        break
        except Exception:
            logger.exception("Erro durante gravação do microfone")
            return None

        if not chunks:
            return None
        return np.concatenate(chunks, axis=0).flatten()
