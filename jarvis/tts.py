"""Síntese de fala do Jarvis (servidor) — Edge TTS (grátis) ou Fish Audio. Devolve MP3 em bytes."""
# ── Mythus Solutions ── Jarvis ── jarvis/tts.py ──────────────────────────────
from __future__ import annotations

import asyncio
import io
import logging

log = logging.getLogger("jarvis.tts")

EDGE_VOICE = "pt-BR-AntonioNeural"
EDGE_RATE = "+8%"
EDGE_VOLUME = "+8%"
EDGE_PITCH = "-12Hz"


class EdgeTTS:
    """Voz grátis da Microsoft (sem chave). Multilíngue, fala português."""

    def __init__(self, voice: str = EDGE_VOICE) -> None:
        self._voice = voice

    def synthesize(self, text: str) -> bytes:
        text = (text or "").strip()
        if not text:
            raise ValueError("Texto vazio para síntese.")
        return asyncio.run(self._synth(text))

    async def _synth(self, text: str) -> bytes:
        import edge_tts

        communicate = edge_tts.Communicate(
            text,
            voice=self._voice,
            rate=EDGE_RATE,
            volume=EDGE_VOLUME,
            pitch=EDGE_PITCH,
        )
        chunks = bytearray()
        async for chunk in communicate.stream():
            if chunk["type"] == "audio":
                chunks.extend(chunk["data"])
        if not chunks:
            raise RuntimeError("Edge TTS devolveu áudio vazio.")
        return bytes(chunks)


class FishTTS:
    """Voz clonada estilo Jarvis (Fish Audio). Requer FISH_API_KEY com saldo."""

    def __init__(self, api_key: str, reference_id: str) -> None:
        if not api_key:
            raise ValueError("FISH_API_KEY não configurada.")
        if not reference_id:
            raise ValueError("FISH_REFERENCE_ID não configurado.")
        self._api_key = api_key
        self._reference_id = reference_id

    def synthesize(self, text: str) -> bytes:
        from fish_audio_sdk import Session, TTSRequest

        text = (text or "").strip()
        if not text:
            raise ValueError("Texto vazio para síntese.")
        session = Session(self._api_key)
        request = TTSRequest(
            text=text,
            reference_id=self._reference_id,
            format="mp3",
            latency="balanced",
        )
        buffer = io.BytesIO()
        for chunk in session.tts(request):
            buffer.write(chunk)
        audio = buffer.getvalue()
        if not audio:
            raise RuntimeError("Fish Audio devolveu áudio vazio.")
        return audio


def build_tts(settings):
    """Escolhe a engine pelo JARVIS_TTS_ENGINE (edge = grátis; fish = voz clonada)."""
    engine = (getattr(settings, "tts_engine", "edge") or "edge").lower()
    if engine == "fish":
        return FishTTS(settings.fish_api_key, settings.fish_reference_id)
    return EdgeTTS()
