"""Gravação do microfone e transcrição com faster-whisper (small, int8, PT-BR)."""
from __future__ import annotations

import logging

import numpy as np
import sounddevice as sd
from faster_whisper import WhisperModel

from audio_utils import TARGET_RATE, negotiate_input, resample_to_target, to_mono

logger = logging.getLogger("jarvis.desktop.listener")

_SAMPLE_RATE    = TARGET_RATE                           # 16 kHz — taxa entregue ao Whisper
_BLOCK_MS       = 32
_SILENCE_RMS    = 0.003                                 # ~−50dBFS
_SILENCE_BLOCKS = int(1.2 * 1000 / _BLOCK_MS)          # 1.2s de silêncio pós-fala
_MIN_TEXT_LEN   = 3                                     # transcrições triviais descartadas


class Listener:
    """Grava do microfone e transcreve em PT com Whisper small."""

    def __init__(self, device: int | None = None) -> None:
        self._device = device
        logger.info(
            "Carregando Whisper small (int8, CPU) — pode demorar no 1.º boot..."
        )
        self._model = WhisperModel("small", device="cpu", compute_type="int8")
        logger.info("Whisper pronto.")

    def listen_and_transcribe(
        self,
        max_duration_sec: float = 15.0,
        pre_speech_sec: float | None = None,
    ) -> str | None:
        """Grava até silêncio pós-fala ou max_duration_sec, transcreve em PT-BR.

        pre_speech_sec: se fornecido, aguarda até este tempo por início de fala
                        antes de desistir; None = sai após 1.2s de silêncio padrão.
        """
        logger.info("Ouvindo...")
        audio = self._record(max_duration_sec, pre_speech_sec)
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
                no_speech_threshold=0.3,
                condition_on_previous_text=False,
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

    def _record(
        self,
        max_duration_sec: float = 15.0,
        pre_speech_sec: float | None = None,
    ) -> np.ndarray | None:
        """Grava blocos de 32ms com VAD simples.

        pre_speech_sec=None (padrão): sai após _SILENCE_BLOCKS blocos silenciosos,
                                      mesmo antes de a fala começar.
        pre_speech_sec=N: aguarda até N segundos por início de fala; após fala
                          detectada, sai com 1.2s de silêncio normal.
        """
        params = negotiate_input(self._device)  # block_ms=32 default
        if params is None:
            return None
        native_rate, channels, block_size = params

        max_blocks = int(max_duration_sec * 1000 / _BLOCK_MS)
        pre_blocks = int(pre_speech_sec * 1000 / _BLOCK_MS) if pre_speech_sec else None
        chunks: list[np.ndarray] = []
        silent_count = 0
        speech_detected = False

        try:
            with sd.InputStream(
                samplerate=native_rate,
                channels=channels,
                dtype="float32",
                blocksize=block_size,
                device=self._device,
            ) as stream:
                for _ in range(max_blocks):
                    block, _ = stream.read(block_size)
                    chunks.append(block.copy())
                    # np.mean() sobre todos os elementos funciona para qualquer shape
                    rms = float(np.sqrt(np.mean(block ** 2)))

                    if rms >= _SILENCE_RMS:
                        silent_count = 0
                        speech_detected = True
                    else:
                        silent_count += 1

                    threshold = (
                        pre_blocks
                        if (not speech_detected and pre_blocks is not None)
                        else _SILENCE_BLOCKS
                    )
                    if silent_count >= threshold:
                        if not speech_detected and pre_blocks is not None:
                            return None  # timeout antes da fala começar
                        break
        except Exception:
            logger.exception("Erro durante gravação do microfone")
            return None

        if not chunks:
            return None

        # Grava na taxa nativa; resample para 16 kHz mono antes de passar ao Whisper.
        all_audio = np.concatenate(chunks, axis=0)
        mono = to_mono(all_audio)
        return resample_to_target(mono, native_rate)
