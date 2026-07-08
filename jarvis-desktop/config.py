"""Configuração do cliente de voz — carregada de voice.env."""
# ── Mythus Solutions ── Jarvis Desktop ── jarvis-desktop/config.py ───────────
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(dotenv_path=Path(__file__).parent / "voice.env")


@dataclass(frozen=True)
class VoiceConfig:
    brain_url: str
    brain_token: str
    clap_sensitivity: float   # limiar_ratio; default 8.0
    audio_device: int | None  # None = dispositivo padrão do sistema
    sample_rate: int          # 16000
    ws_port: int              # porta do WebSocket para o HUD


def load_config() -> VoiceConfig:
    raw_device = os.getenv("AUDIO_DEVICE")
    return VoiceConfig(
        brain_url=os.getenv("BRAIN_URL", "http://127.0.0.1:8787"),
        brain_token=os.getenv("BRAIN_TOKEN", ""),
        clap_sensitivity=float(os.getenv("CLAP_SENSITIVITY", "8.0")),
        audio_device=int(raw_device) if raw_device else None,
        sample_rate=int(os.getenv("SAMPLE_RATE", "16000")),
        ws_port=int(os.getenv("HUD_WS_PORT", "8765")),
    )
