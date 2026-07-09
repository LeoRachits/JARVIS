# Jarvis HUD

Orb ciano flutuante estilo **reator arc do Homem de Ferro** — janela transparente,
sem borda, sempre-no-topo e click-through que reage em tempo real aos estados do Jarvis.

## Como funciona

O HUD é um **cliente WebSocket** que conecta em `ws://127.0.0.1:8765` (porta do
`jarvis-desktop`). Não cria servidor; apenas escuta e anima.

| Evento recebido | Efeito visual |
|---|---|
| `{"type":"state","value":"idle"}` | Núcleo respira devagar (~0.2Hz), partículas lentas |
| `{"type":"state","value":"listening"}` | Anel expande, partículas aceleram, brilho forte |
| `{"type":"state","value":"thinking"}` | Partículas giram rápido + arco de varredura (radar) |
| `{"type":"state","value":"speaking"}` | Núcleo pulsa com o áudio real (`level`) |
| `{"type":"state","value":"error"}` | Pulso vermelho duplo rápido → volta a idle em 2.5s |
| `{"type":"level","value":0.0–1.0}` | Alimenta o pulso do speaking (RMS do microfone) |
| `{"type":"transcript","text":"..."}` | Mostra o que você falou na legenda |
| `{"type":"delta","text":"..."}` | Concatena a resposta do Jarvis na legenda |

## Pré-requisitos

- **Node.js 18+** — https://nodejs.org
- Windows 10/11 (macOS e Linux também funcionam; transparência depende do compositor)

## Instalação

```bat
cd jarvis-hud
npm install
```

## Execução

```bat
npm start
```

Uma janela flutuante aparece no **canto inferior direito**, sem barra de título,
transparente. Cliques passam direto para as janelas por baixo.

### Porta customizada

```bat
set HUD_PORT=9000 && npm start
```

(O jarvis-desktop expõe a porta configurada em `HUD_PORT` ou `HUD_WS_PORT` no
`jarvis-desktop/voice.env`. Padrão: 8765.)

## Testar sem o Jarvis rodando

```bat
# Terminal 1 — servidor de teste
cd jarvis-hud
pip install websockets
python test-hud.py

# Terminal 2 — HUD
npm start
```

O `test-hud.py` percorre todos os estados (idle → listening → thinking → speaking →
error) com dados simulados, incluindo pulsos de áudio para o estado speaking.

## Integração com o jarvis-desktop

**Abordagem atual (recomendada): apps separados.**

1. Terminal A: `cd jarvis-desktop && python main.py`
2. Terminal B: `cd jarvis-hud && npm start`

O HUD reconecta automaticamente a cada 2s até o desktop subir — ordem não importa.

**Alternativa futura (opcional):** spawnar o HUD automaticamente no `main.py` do
jarvis-desktop:

```python
# jarvis-desktop/main.py — adicionar no final de run(), após self._hud.start()
import subprocess, os
subprocess.Popen(
    ['npm', '--prefix', str(Path(__file__).parent.parent / 'jarvis-hud'), 'start'],
    env={**os.environ, 'HUD_PORT': str(self._cfg.hud_port)},
)
```

Não foi acoplado agora para manter os dois projetos independentes e facilitar o
desenvolvimento separado.

## Estrutura

```
jarvis-hud/
├── main.js        — processo principal Electron (BrowserWindow)
├── index.html     — orb (canvas 2D) + cliente WebSocket
├── test-hud.py    — servidor WS de teste; simula todos os estados
├── package.json
├── .gitignore
└── README.md
```
