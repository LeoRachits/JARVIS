"""
Smoke test do cérebro do Jarvis.
Pergunta 1: valida web_search (notícias + fontes).
Pergunta 2: valida web_fetch (abre URL e resume).
"""
# ── Mythus Solutions ── Jarvis ── smoke_test.py ──────────────────────────────
import sys
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from jarvis.config import load_settings
from jarvis.brain import Brain

PERGUNTAS = [
    (
        "web_search",
        "Quais são as principais notícias do Brasil hoje? "
        "Pesquise na web e cite as fontes.",
    ),
    (
        "web_fetch",
        "Abra e resuma esta página: https://www.anthropic.com/news",
    ),
]
SESSION = "smoke"

settings = load_settings()
brain = Brain(settings)

# Limpa sessão anterior para evitar histórico contaminado.
brain.reset(SESSION)

print("=" * 60)
print("JARVIS SMOKE TEST")
print(f"Modelo: {settings.model}")
print("=" * 60)

for label, pergunta in PERGUNTAS:
    print(f"\n[{label.upper()}] {pergunta}")
    print("-" * 60)
    resposta = brain.chat(SESSION, pergunta)
    print(resposta)
    print()

print("=" * 60)
print("SMOKE TEST CONCLUÍDO")
