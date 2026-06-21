"""
Smoke test do cérebro do Jarvis.
Envia uma pergunta que força busca na web e imprime a resposta completa.
"""
# ── Mythus Solutions ── Jarvis ── smoke_test.py ──────────────────────────────
import sys
import os

# Garante que a raiz do projeto está no path (permite rodar de qualquer CWD)
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from jarvis.config import load_settings
from jarvis.brain import Brain

PERGUNTA = (
    "Quais são as principais notícias do Brasil hoje? "
    "Pesquise na web e cite as fontes."
)
SESSION = "smoke"

print("=" * 60)
print("JARVIS SMOKE TEST")
print("=" * 60)
print(f"Pergunta: {PERGUNTA}")
print("-" * 60)

settings = load_settings()
print(f"Modelo   : {settings.model}")
print(f"Max tokens: {settings.max_tokens}")
print("-" * 60)

brain = Brain(settings)
resposta = brain.chat(SESSION, PERGUNTA)

print("Resposta:")
print(resposta)
print("=" * 60)
print("SMOKE TEST CONCLUÍDO")
