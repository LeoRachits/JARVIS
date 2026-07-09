"""Teste local do /speak — gera scripts/teste_voz.mp3 com a engine configurada."""
# ── Mythus Solutions ── Jarvis ── scripts/teste_voz.py ───────────────────────
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from jarvis.config import load_settings
from jarvis.tts import build_tts

OUT = os.path.join(os.path.dirname(__file__), "teste_voz.mp3")

settings = load_settings()
print(f"Engine : {settings.tts_engine}")

tts = build_tts(settings)
print("Sintetizando...")
audio = tts.synthesize("Olá, senhor. Aqui é o Jarvis, teste de voz.")

with open(OUT, "wb") as f:
    f.write(audio)

size = os.path.getsize(OUT)
with open(OUT, "rb") as f:
    header = f.read(3)

is_id3  = header[:3] == b"ID3"
is_mpeg = header[0] == 0xFF and (header[1] & 0xE0) == 0xE0

print(f"Arquivo : {OUT}")
print(f"Tamanho : {size} bytes")
print(f"Cabeçalho MP3 válido: {'sim (ID3)' if is_id3 else 'sim (MPEG sync)' if is_mpeg else 'NÃO RECONHECIDO'}")
