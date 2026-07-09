"""Simula o jarvis-desktop para testar o HUD sem o Jarvis completo rodando.

Abre um servidor WebSocket em ws://127.0.0.1:8765 e percorre todos os estados:
  idle → listening → thinking → speaking → idle → error → idle

Uso:
    pip install websockets   # se ainda não tiver
    python test-hud.py
"""
import asyncio
import json
import math


async def simular(websocket):
    print("[teste] HUD conectado! Iniciando simulação dos estados...")

    async def envia(obj):
        await websocket.send(json.dumps(obj))

    # ── idle ──────────────────────────────────────────────────────────────────
    await envia({"type": "state", "value": "idle"})
    print("[teste] → idle (3s)")
    await asyncio.sleep(3)

    # ── listening ─────────────────────────────────────────────────────────────
    await envia({"type": "state", "value": "listening"})
    await envia({"type": "transcript", "text": "liga o ar do quarto"})
    print("[teste] → listening + transcript (2s)")
    await asyncio.sleep(2)

    # ── thinking + deltas de resposta ─────────────────────────────────────────
    await envia({"type": "state", "value": "thinking"})
    print("[teste] → thinking (deltas chegando...)")
    for palavra in "Ligando o ar-condicionado do quarto agora, senhor.".split():
        await envia({"type": "delta", "text": palavra + " "})
        await asyncio.sleep(0.18)
    await asyncio.sleep(0.5)

    # ── speaking + nível de áudio simulado ───────────────────────────────────
    await envia({"type": "state", "value": "speaking"})
    print("[teste] → speaking (60 pulsos de áudio)")
    for i in range(60):
        lvl = round(abs(math.sin(i * 0.28)) * 0.88, 3)
        await envia({"type": "level", "value": lvl})
        await asyncio.sleep(0.05)
    await envia({"type": "level", "value": 0})

    # ── idle ──────────────────────────────────────────────────────────────────
    await envia({"type": "state", "value": "idle"})
    print("[teste] → idle (3s)")
    await asyncio.sleep(3)

    # ── error (volta sozinho a idle após 2.5s no HUD) ─────────────────────────
    await envia({"type": "state", "value": "error"})
    print("[teste] → error (HUD volta a idle em 2.5s sozinho)")
    await asyncio.sleep(4)

    # ── idle final ─────────────────────────────────────────────────────────────
    await envia({"type": "state", "value": "idle"})
    print("[teste] → idle. Simulação concluída — conexão mantida aberta.")
    await asyncio.Future()  # mantém conectado indefinidamente


async def main():
    try:
        import websockets  # noqa: F401
    except ImportError:
        print("Instale websockets primeiro:  pip install websockets")
        return

    import websockets as ws

    print(f"Servidor WS de teste em ws://127.0.0.1:8765")
    print("Abra o HUD com:  npm start   (em outro terminal, dentro de jarvis-hud/)")
    print("Aguardando conexão do HUD...\n")

    async with ws.serve(simular, "127.0.0.1", 8765):
        await asyncio.Future()


if __name__ == "__main__":
    asyncio.run(main())
