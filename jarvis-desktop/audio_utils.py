"""Adapta captura de microfone ao dispositivo: detecta taxa/canais nativos,
faz downmix para mono e reamostragem para 16 kHz antes de entregar ao Vosk/Whisper.
"""
from __future__ import annotations

import logging
from math import gcd

import numpy as np
import sounddevice as sd

logger = logging.getLogger("jarvis.desktop.audio_utils")

TARGET_RATE = 16_000   # Hz — taxa esperada pelo Vosk e pelo Whisper
_BLOCK_MS   = 32       # duração de cada bloco de captura (ms)

# Taxas de fallback tentadas quando a taxa nativa do device falha.
_RATE_FALLBACKS: tuple[int, ...] = (48_000, 44_100, 16_000)


# ── Consulta de capabilities ──────────────────────────────────────────────────

def probe_device(device: int | None) -> tuple[int, int]:
    """Retorna (taxa_nativa_Hz, max_canais_entrada) do dispositivo.

    Consulta o device especificado; se device=None, usa o de entrada padrão.
    Fallback seguro: (16000, 1) caso a consulta falhe.
    """
    try:
        info = (
            sd.query_devices(kind="input")
            if device is None
            else sd.query_devices(device)
        )
        rate = int(info["default_samplerate"])
        ch   = max(1, int(info["max_input_channels"]))
        return rate, ch
    except Exception as exc:
        logger.warning(
            "Não consegui consultar device %s (%s) — assumindo 16000 Hz, 1 canal.",
            device if device is not None else "padrão",
            exc,
        )
        return TARGET_RATE, 1


# ── Negociação automática ──────────────────────────────────────────────────────

def negotiate_input(
    device: int | None,
    block_ms: int = _BLOCK_MS,
) -> tuple[int, int, int] | None:
    """Acha a primeira combinação (taxa_Hz, canais, block_size) que o device aceita.

    Estratégia:
      • Taxa: nativa primeiro; se falhar, tenta 48k, 44.1k e 16k.
      • Canais: tenta 1 (mono) primeiro; se o device exigir mais, tenta max_input_channels.

    Loga em PT qual combinação abriu com sucesso.
    Retorna None se todas as tentativas falharem — o chamador lida sem travar.
    """
    native_rate, max_ch = probe_device(device)
    dev_label = str(device) if device is not None else "padrão"

    rates = [native_rate] + [r for r in _RATE_FALLBACKS if r != native_rate]
    ch_list = [1, max_ch] if max_ch > 1 else [1]

    for rate in rates:
        for ch in ch_list:
            bs = max(1, int(rate * block_ms / 1000))
            try:
                with sd.InputStream(
                    samplerate=rate,
                    channels=ch,
                    dtype="float32",
                    blocksize=bs,
                    device=device,
                ):
                    pass  # abre/fecha só para validar — sem ler dados
                logger.info(
                    "Microfone aberto: device=%s, %d Hz, %d canal(is) "
                    "→ resample para %d Hz mono.",
                    dev_label, rate, ch, TARGET_RATE,
                )
                return rate, ch, bs
            except Exception as exc:
                logger.debug(
                    "Tentativa device=%s %d Hz %dch rejeitada: %s",
                    dev_label, rate, ch, exc,
                )

    logger.warning(
        "Não foi possível abrir o microfone (device=%s). "
        "Verifique se está conectado e disponível; "
        "tente ajustar AUDIO_DEVICE no voice.env ou deixe vazio para usar o padrão.",
        dev_label,
    )
    return None


# ── Conversão de áudio ─────────────────────────────────────────────────────────

def to_mono(data: np.ndarray) -> np.ndarray:
    """Downmix multi-canal → mono float32 por média dos canais.

    Aceita shape (frames,) ou (frames, channels).
    """
    if data.ndim == 1:
        return data.astype(np.float32, copy=False)
    return data.mean(axis=1).astype(np.float32)


def resample_to_target(mono: np.ndarray, native_rate: int) -> np.ndarray:
    """Reamostrar float32 mono de native_rate para TARGET_RATE (16 kHz).

    Usa scipy.signal.resample_poly (filtro anti-aliasing correto) quando disponível;
    fallback para interpolação linear numpy (aceitável para fala < 8 kHz).
    """
    if native_rate == TARGET_RATE:
        return mono.astype(np.float32, copy=False)
    try:
        from scipy.signal import resample_poly  # type: ignore[import]
        g    = gcd(TARGET_RATE, native_rate)
        up   = TARGET_RATE // g
        down = native_rate // g
        return resample_poly(mono, up, down).astype(np.float32)
    except ImportError:
        target_len = max(1, int(round(len(mono) * TARGET_RATE / native_rate)))
        return np.interp(
            np.linspace(0, len(mono) - 1, target_len),
            np.arange(len(mono)),
            mono,
        ).astype(np.float32)


def block_to_vosk_bytes(block: np.ndarray, native_rate: int) -> bytes:
    """Bloco float32 capturado (qualquer taxa/canais) → bytes int16 16 kHz mono para Vosk."""
    mono      = to_mono(block)
    resampled = resample_to_target(mono, native_rate)
    clipped   = np.clip(resampled, -1.0, 1.0)
    return (clipped * 32_767).astype(np.int16).tobytes()
