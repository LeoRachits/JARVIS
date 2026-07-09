"""Detecção de palma dupla por DSP — limiar adaptativo de RMS + janela de tempo."""
from __future__ import annotations

import logging
import threading
import time
from collections import deque
from typing import Callable

import numpy as np
import sounddevice as sd

logger = logging.getLogger("jarvis.desktop.clap_detector")

_SAMPLE_RATE = 16_000
_BLOCK_MS = 32
_BLOCK_SIZE = int(_SAMPLE_RATE * _BLOCK_MS / 1000)   # 512 amostras por bloco
_NOISE_WINDOW = 15                                     # ~500ms de histórico
_MAX_IMPULSE_MS = 80                                   # palma = impulso < 80ms
_CLAP_MIN_GAP_MS = 200                                 # 2 palmas simultâneas = ruído
_CLAP_MAX_GAP_MS = 900                                 # janela para palma dupla
_INIT_NOISE = 0.001                                    # piso inicial conservador


class ClapDetector:
    """Detecta palma dupla via RMS adaptativo sem ML.

    Algoritmo:
    1. Por bloco (32ms): calcula RMS.
    2. Piso = média dos últimos ~500ms de blocos SILENCIOSOS (adaptativo).
    3. Candidato a palma = RMS > sensitivity * piso E duração < 80ms.
    4. Palma dupla = 2 candidatos com intervalo entre 200ms e 900ms.

    Durante 'speaking', set_barge_in_mode(True) dobra o limiar para ignorar
    o som do próprio speaker. Palma dupla nesse modo dispara barge-in.
    """

    def __init__(
        self,
        sensitivity: float = 8.0,
        device: int | None = None,
        on_double_clap: Callable[[], None] | None = None,
    ) -> None:
        self._sensitivity = sensitivity
        self._device = device
        self._on_double_clap = on_double_clap

        self._noise_history: deque[float] = deque(
            [_INIT_NOISE] * _NOISE_WINDOW, maxlen=_NOISE_WINDOW
        )
        self._in_impulse = False
        self._impulse_start: float | None = None
        self._first_clap_time: float | None = None
        self._barge_in_mode = False
        self._lock = threading.Lock()
        self._stream: sd.InputStream | None = None

    def register_on_double_clap(self, callback: Callable[[], None]) -> None:
        self._on_double_clap = callback

    def start(self) -> None:
        self._stream = sd.InputStream(
            samplerate=_SAMPLE_RATE,
            channels=1,
            dtype="float32",
            blocksize=_BLOCK_SIZE,
            device=self._device,
            callback=self._audio_callback,
        )
        self._stream.start()
        logger.info("ClapDetector iniciado (sensitivity=%.1f)", self._sensitivity)

    def stop(self) -> None:
        if self._stream:
            self._stream.stop()
            self._stream.close()
            self._stream = None
        logger.info("ClapDetector parado.")

    def set_barge_in_mode(self, enabled: bool) -> None:
        """Dobra o limiar durante speaking para ignorar o som do próprio speaker."""
        with self._lock:
            self._barge_in_mode = enabled

    # ------------------------------------------------------------------ #
    # Callback de áudio — roda na thread do sounddevice, não na main
    # ------------------------------------------------------------------ #
    def _audio_callback(
        self,
        indata: np.ndarray,
        frames: int,
        time_info: object,
        status: sd.CallbackFlags,
    ) -> None:
        rms = float(np.sqrt(np.mean(indata ** 2)))
        now = time.monotonic()

        with self._lock:
            noise_floor = float(np.mean(self._noise_history))
            ratio = self._sensitivity * (2.0 if self._barge_in_mode else 1.0)
            threshold = noise_floor * ratio
            is_loud = rms > threshold

            # Só blocos silenciosos alimentam o piso adaptativo
            if not is_loud:
                self._noise_history.append(rms)

            if is_loud and not self._in_impulse:
                self._in_impulse = True
                self._impulse_start = now

            elif not is_loud and self._in_impulse:
                duration_ms = (
                    (now - self._impulse_start) * 1000 if self._impulse_start else 999.0
                )
                self._in_impulse = False
                self._impulse_start = None

                if duration_ms < _MAX_IMPULSE_MS:
                    self._on_candidate(now)

    def _on_candidate(self, now: float) -> None:
        """Chamado (com lock) ao detectar um impulso curto candidato a palma."""
        if self._first_clap_time is None:
            self._first_clap_time = now
            logger.debug("Palma 1 detectada — aguardando palma 2")
            return

        gap_ms = (now - self._first_clap_time) * 1000

        if gap_ms > _CLAP_MAX_GAP_MS:
            # Janela expirou — esta palma vira a primeira
            self._first_clap_time = now
            logger.debug("Janela expirada. Palma 1 resetada (gap=%.0fms)", gap_ms)
            return

        if gap_ms >= _CLAP_MIN_GAP_MS:
            # PALMA DUPLA confirmada!
            self._first_clap_time = None
            logger.info("Palma dupla confirmada (gap=%.0fms)", gap_ms)
            if self._on_double_clap:
                threading.Thread(
                    target=self._on_double_clap, daemon=True, name="clap-cb"
                ).start()
        # gap < MIN_GAP: muito próximas, ignora


# ─────────────────────────────────────────────────────────────────────────────
# Teste unitário embutido
# ─────────────────────────────────────────────────────────────────────────────
def _run_tests() -> None:
    """Simula blocos de áudio e valida a lógica sem hardware."""
    import time as _time

    fired: list[bool] = []

    def _make_detector() -> ClapDetector:
        d = ClapDetector(sensitivity=8.0)
        d._on_double_clap = lambda: fired.append(True)  # noqa: SLF001
        return d

    NOISE_RMS = 0.001
    CLAP_RMS = 0.05   # 50x acima do piso → dispara com sensitivity=8

    def _inject(detector: ClapDetector, rms: float, duration_ms: float) -> None:
        """Simula um bloco com dado RMS, marcando início e fim do impulso."""
        now = _time.monotonic()
        # Simula 'is_loud=True' → _in_impulse começa
        with detector._lock:  # noqa: SLF001
            detector._noise_history.append(NOISE_RMS)
            detector._in_impulse = True
            detector._impulse_start = now - duration_ms / 1000

        _time.sleep(0.001)

        # Simula 'is_loud=False' → impulso encerra, candidato avaliado
        with detector._lock:  # noqa: SLF001
            dur = (now - detector._impulse_start) * 1000 if detector._impulse_start else 999
            detector._in_impulse = False
            detector._impulse_start = None
            if dur < _MAX_IMPULSE_MS:
                detector._on_candidate(now)

    # ── Teste 1: palma dupla válida (gap 400ms) ────────────────────────
    fired.clear()
    d = _make_detector()
    _inject(d, CLAP_RMS, 30)
    _time.sleep(0.4)
    _inject(d, CLAP_RMS, 30)
    _time.sleep(0.05)
    assert fired, "FALHA: palma dupla dentro da janela não disparou"
    print("PASS: palma dupla valida (400ms) dispara")

    # ── Teste 2: palma única — não dispara ────────────────────────────
    fired.clear()
    d = _make_detector()
    _inject(d, CLAP_RMS, 30)
    _time.sleep(0.05)
    assert not fired, "FALHA: palma unica disparou erroneamente"
    print("PASS: palma unica nao dispara")

    # ── Teste 3: duas palmas com gap > 900ms — não dispara ────────────
    fired.clear()
    d = _make_detector()
    _inject(d, CLAP_RMS, 30)
    _time.sleep(1.1)
    _inject(d, CLAP_RMS, 30)
    _time.sleep(0.05)
    assert not fired, "FALHA: gap > 900ms disparou erroneamente"
    print("PASS: duas palmas fora da janela (1100ms) nao dispararam")

    # ── Teste 4: impulso longo (voz) — não dispara ────────────────────
    fired.clear()
    d = _make_detector()
    _inject(d, CLAP_RMS, 150)   # 150ms > MAX_IMPULSE_MS=80ms → nao e palma
    _time.sleep(0.05)
    assert not fired, "FALHA: impulso longo foi aceito como palma"
    print("PASS: impulso longo (voz) nao dispara")

    print("\nTodos os testes passaram.")


if __name__ == "__main__":
    _run_tests()
