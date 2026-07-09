# Jarvis Desktop — Cliente de Voz

Cliente de voz local que ativa por **wake word "Jarvis"** (offline, via Vosk), ouve,
pensa (via `/chat/stream`) e fala a resposta em streaming de frases.

## Hardware alvo

ASUS Vivobook, Intel i7-1255U, 16 GB RAM, Intel Iris Xe (sem CUDA).
Whisper roda em CPU com `compute_type="int8"` — boot ~5s, resposta ~1-2s por frase.

## Pré-requisitos

- Python 3.11+
- O servidor do cérebro rodando (`jarvis/server.py` na raiz do repo)
- Microfone e saída de áudio configurados no Windows
- Modelo Vosk PT-BR (veja abaixo)

## Instalação

```bat
cd jarvis-desktop
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
```

### Download do modelo Vosk (obrigatório)

1. Acesse https://alphacephei.com/vosk/models
2. Baixe **vosk-model-small-pt-0.3** (≈ 31 MB)
3. Descompacte dentro de `jarvis-desktop/`:

```
jarvis-desktop/
└── models/
    └── vosk-model-small-pt-0.3/
        ├── am/
        ├── conf/
        ├── graph/
        └── ...
```

> Caminho configurável via `WAKE_MODEL_PATH` no `voice.env`.

## Configuração

```bat
copy voice.env.example voice.env
```

Edite `voice.env`:

| Variável | Descrição | Padrão |
|---|---|---|
| `BRAIN_URL` | URL do servidor do cérebro | `http://127.0.0.1:8787` |
| `BRAIN_TOKEN` | Token Bearer (vazio se sem auth) | |
| `WAKE_MODEL_PATH` | Caminho do modelo Vosk | `models/vosk-model-small-pt-0.3` |
| `FOLLOWUP_WINDOW_SEC` | Segundos de espera por pergunta de acompanhamento | `8` |
| `AUDIO_DEVICE` | Índice do microfone (vazio = padrão) | |
| `HUD_PORT` | Porta WebSocket para o HUD | `8765` |

Para listar dispositivos de áudio:

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

| Ação | Como fazer |
|---|---|
| Ativar | Diga **"Jarvis"** |
| Fazer pergunta de acompanhamento | Fale dentro de 8s após a resposta (sem dizer "Jarvis" de novo) |
| Interromper fala (barge-in) | Diga **"Jarvis"** durante a resposta |
| HUD (SPEC-03) | Conectar em `ws://127.0.0.1:8765` |

## Máquina de estados

```
idle ──(wake word)──► listening ──(texto)──► thinking ──► speaking ──► followup
                                └─(silêncio)──► idle                  │   │
                                                       (barge-in)──►  │   └─(fala)──► thinking
                                                                       └─(silêncio 8s)──► idle
```

## Testes rápidos

```bat
# Testa lógica do detector de palma (sem hardware — legado, mantido por referência):
python clap_detector.py

# Testa conexão com o cérebro (servidor deve estar rodando):
python -c "
from brain_client import BrainClient
for ev in BrainClient('http://127.0.0.1:8787').stream_chat('qual a capital da Franca', 'desktop'):
    print(ev)
"

# Verifica sintaxe de todos os módulos:
python -m py_compile config.py hud_bridge.py brain_client.py clap_detector.py listener.py speaker.py wake_word.py main.py
```

## Estrutura

```
jarvis-desktop/
├── main.py           — orquestrador (máquina de estados)
├── wake_word.py      — detecção de wake word offline (Vosk)
├── clap_detector.py  — detecção de palma dupla por DSP (referência)
├── listener.py       — gravação + transcrição (Whisper small int8)
├── speaker.py        — TTS em streaming de frases
├── hud_bridge.py     — servidor WebSocket para o HUD
├── brain_client.py   — cliente SSE para /chat/stream
├── config.py         — lê voice.env
├── requirements.txt
├── voice.env.example
├── models/           — modelo(s) Vosk (não versionado)
└── logs/             — criado automaticamente
```
