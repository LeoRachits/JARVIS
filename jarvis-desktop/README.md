# Jarvis Desktop — Cliente de Voz

Cliente de voz local que ativa por **palma dupla**, ouve, pensa (via `/chat/stream`)
e fala a resposta em streaming de frases.

## Hardware alvo

ASUS Vivobook, Intel i7-1255U, 16 GB RAM, Intel Iris Xe (sem CUDA).
Whisper roda em CPU com `compute_type="int8"` — boot ~5s, resposta ~1-2s por frase.

## Pré-requisitos

- Python 3.11+
- O servidor do cérebro rodando (`jarvis/server.py` na raiz do repo)
- Microfone e saída de áudio configurados no Windows

## Instalação

```bat
cd jarvis-desktop
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

## Configuração

```bat
copy voice.env.example voice.env
```

Edite `voice.env`:
- `BRAIN_URL` — URL do servidor (padrão: `http://127.0.0.1:8787`)
- `BRAIN_TOKEN` — token Bearer se `JARVIS_API_TOKEN` estiver definido no `.env` do cérebro
- `CLAP_SENSITIVITY` — aumente se disparar com ruído ambiental (default: 8.0)
- `AUDIO_DEVICE` — índice do microfone (vazio = padrão do sistema)

Para listar os dispositivos de áudio disponíveis:

```bat
python -c "import sounddevice; print(sounddevice.query_devices())"
```

## Execução

```bat
# Com console (desenvolvimento):
python main.py

# Sem console (produção):
pythonw.exe main.py
```

### Boot automático no logon (Windows)

1. Abra o **Agendador de Tarefas** (`taskschd.msc`)
2. Criar Tarefa Básica → "Jarvis Desktop"
3. Gatilho: "Ao fazer logon"
4. Ação: Iniciar programa
   - Programa: `C:\...\jarvis-desktop\.venv\Scripts\pythonw.exe`
   - Argumentos: `main.py`
   - Iniciar em: `C:\...\jarvis-desktop\`
5. Em "Condições": desmarque "Iniciar somente se o computador estiver em alimentação CA"

## Uso

| Ação | Comando |
|---|---|
| Ativar | Duas palmas (200–900ms de intervalo) |
| Interromper fala (barge-in) | Duas palmas durante a resposta |
| HUD (SPEC-03) | Conectar em `ws://127.0.0.1:8765` |

## Máquina de estados

```
idle ──(palma dupla)──► listening ──(transcrição)──► thinking ──► speaking ──► idle
                                  └─(silêncio)──► idle                ▲
                                                           (barge-in)──► listening
```

## Testes rápidos

```bat
# Testa lógica do detector de palma (sem hardware):
python clap_detector.py

# Testa conexão com o cérebro (servidor deve estar rodando):
python -c "
from brain_client import BrainClient
for ev in BrainClient('http://127.0.0.1:8787').stream_chat('qual a capital da Franca', 'desktop'):
    print(ev)
"

# Verifica sintaxe de todos os módulos:
python -m py_compile config.py hud_bridge.py brain_client.py clap_detector.py listener.py speaker.py main.py
```

## Estrutura

```
jarvis-desktop/
├── main.py           — orquestrador (máquina de estados)
├── clap_detector.py  — detecção de palma dupla por DSP
├── listener.py       — gravação + transcrição (Whisper small int8)
├── speaker.py        — TTS em streaming de frases
├── hud_bridge.py     — servidor WebSocket para o HUD
├── brain_client.py   — cliente SSE para /chat/stream
├── config.py         — lê voice.env
├── requirements.txt
├── voice.env.example
└── logs/             — criado automaticamente
```
