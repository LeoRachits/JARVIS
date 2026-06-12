"""Converse com o Jarvis direto no terminal — jeito mais rápido de testar.

Uso:  python cli.py
"""
from __future__ import annotations

from jarvis.brain import Brain
from jarvis.config import load_settings


def main() -> None:
    settings = load_settings()
    brain = Brain(settings)
    print(f"{settings.jarvis_name} online. (digite 'sair' para encerrar)\n")

    while True:
        try:
            user = input(f"{settings.user_name}: ").strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n{settings.jarvis_name}: Até logo.")
            break

        if user.lower() in {"sair", "exit", "quit"}:
            print(f"{settings.jarvis_name}: Às ordens. Até logo.")
            break
        if not user:
            continue

        reply = brain.chat(session_id="terminal", user_message=user)
        print(f"{settings.jarvis_name}: {reply}\n")


if __name__ == "__main__":
    main()
