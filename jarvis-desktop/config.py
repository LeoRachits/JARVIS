"""Configuração do cliente de voz — carregada de voice.env."""
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
    wake_model_path: str        # caminho do modelo Vosk PT-BR
    followup_window_sec: float  # janela de pré-fala no follow-up (seg)
    audio_device: int | None    # None = dispositivo padrão do sistema
    sample_rate: int            # 16000
    hud_port: int               # porta WebSocket para o HUD


def load_config() -> VoiceConfig:
    raw_device = os.getenv("AUDIO_DEVICE")
    return VoiceConfig(
        brain_url=os.getenv("BRAIN_URL", "http://127.0.0.1:8787"),
        brain_token=os.getenv("BRAIN_TOKEN", ""),
        wake_model_path=os.getenv(
            "WAKE_MODEL_PATH", "models/vosk-model-small-pt-0.3"
        ),
        followup_window_sec=float(os.getenv("FOLLOWUP_WINDOW_SEC", "8.0")),
        audio_device=int(raw_device) if raw_device else None,
        sample_rate=int(os.getenv("SAMPLE_RATE", "16000")),
        hud_port=int(os.getenv("HUD_PORT", os.getenv("HUD_WS_PORT", "8765"))),
    )
