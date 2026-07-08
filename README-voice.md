# Jarvis — Camada de Voz

Transforma o cérebro (texto + memória + web) num assistente que **ouve e fala**,
estilo filme. É um **cliente**: só conversa com o cérebro pelo endpoint `/chat`.
Pode rodar na mesma máquina do cérebro ou em outra (basta apontar `JARVIS_BRAIN_URL`).

```
"Hey Jarvis"  ─►  ouvir (Whisper)  ─►  /chat (cérebro)  ─►  falar (Piper/ElevenLabs)
   wakeword         fala→texto            HTTP                texto→fala
```

## Camadas (cada uma é trocável)

| Bloco | Arquivo | Tecnologia (padrão) | Grátis? |
|---|---|---|---|
| Palavra de ativação | `voice/wakeword.py` | openWakeWord (`hey_jarvis`) | sim, local |
| Ouvir (fim de fala) | `voice/recorder.py` | webrtcvad | sim, local |
| Fala → texto | `voice/stt.py` | faster-whisper | sim, local |
| Pensar | `voice/brain_client.py` | HTTP `/chat` (cérebro) | — |
| Falar | `voice/tts.py` | Piper (ou ElevenLabs) | Piper sim / ElevenLabs pago |

## 1. Instalar

> A voz tem dependências de áudio que **não** vão para a máquina que só hospeda o
> cérebro. Instale isto **no PC com microfone e alto-falante**.

```bash
pip install -r requirements-voice.txt
```

Dependências de sistema (uma vez):

- **Linux:** `sudo apt install portaudio19-dev ffmpeg` (PortAudio para o microfone).
- **Windows:** normalmente funciona direto; se faltar áudio, instale o
  [Microsoft Visual C++ Redistributable].
- **macOS:** `brew install portaudio`.

## 2. Baixar uma voz do Piper (PT-BR)

O Piper precisa de um modelo de voz (`.onnx` + `.onnx.json`). Baixe um par PT-BR
(ex.: `pt_BR-faber-medium`) do repositório oficial de vozes do Piper no Hugging Face,
coloque numa pasta `voices/` e aponte o `.env`:

```
PIPER_MODEL=./voices/pt_BR-faber-medium.onnx
```

O arquivo `.onnx.json` deve ficar **ao lado** do `.onnx`, com o mesmo nome.

> Prefere voz premium? Use `TTS_ENGINE=elevenlabs` e preencha `ELEVENLABS_API_KEY`
> e `ELEVENLABS_VOICE_ID`. Nesse caso o Piper não é necessário.

## 3. Configurar

Anexe o conteúdo de `voice.env.example` ao seu `.env` e ajuste:

- `JARVIS_BRAIN_URL` — onde o cérebro está (mesma máquina: `http://localhost:8787`).
- `JARVIS_API_TOKEN` — **o mesmo** token do servidor do cérebro.
- `VOICE_SESSION_ID` — use `default` para compartilhar memória com os outros corpos.
- `PIPER_MODEL` — caminho do `.onnx` baixado.

Descubra o microfone certo, se precisar:

```bash
python -c "import sounddevice as sd; print(sd.query_devices())"
# coloque o índice em VOICE_MIC_DEVICE
```

## 4. Rodar

Ligue o cérebro primeiro (no PC, Pi ou nuvem):

```bash
uvicorn jarvis.server:app --host 0.0.0.0 --port 8787
```

Depois, a voz:

```bash
python voice_run.py
```

Diga **"Hey Jarvis"**, espere o bip e fale. Ele transcreve, manda para o cérebro
(que pode pesquisar na web) e responde falando. `Ctrl+C` encerra.

> Primeira execução baixa os modelos do openWakeWord e do Whisper — pode demorar.

## 5. Subir junto com o PC

A voz é um serviço que "fica sempre escutando" — trate como serviço gerenciado,
não como um terminal aberto.

- **Windows:** Agendador de Tarefas, gatilho "ao fazer logon", ação
  `python C:\caminho\voice_run.py` (use o Python do seu ambiente). Marque
  "Executar com privilégios mais altos" só se realmente precisar.
- **Linux (Pi/VPS):** crie um serviço **systemd** com `Restart=always` e
  `systemctl enable`. Lembre que voz precisa de hardware de áudio — geralmente
  roda no **seu PC**, enquanto o cérebro pode estar no Pi/Oracle.

Exemplo de unit systemd (ajuste caminhos e usuário):

```ini
[Unit]
Description=Jarvis Voice
After=network-online.target sound.target

[Service]
Type=simple
User=SEU_USUARIO
WorkingDirectory=/home/SEU_USUARIO/jarvis-brain
ExecStart=/home/SEU_USUARIO/jarvis-brain/.venv/bin/python voice_run.py
Restart=always
RestartSec=5

[Install]
WantedBy=default.target
```

## Ajustes finos (qualidade x latência)

- **Whisper:** `tiny`/`base` = mais rápido, menos preciso; `medium` = melhor, mais
  pesado. Com GPU, use `WHISPER_DEVICE=cuda` e `WHISPER_COMPUTE_TYPE=float16`.
- **Disparos falsos** da palavra de ativação: suba `WAKEWORD_THRESHOLD` (ex.: 0.6).
- **Ele corta sua fala cedo:** aumente `VAD_SILENCE_MS` (ex.: 1000–1200).
- **Demora para "fechar" a fala:** diminua `VAD_SILENCE_MS`.

## Como estender

- **Outra palavra de ativação:** treine/baixe outro modelo openWakeWord e troque
  `WAKEWORD_MODEL`.
- **Outro motor de voz:** implemente a interface `TTS` (método `speak`) em
  `voice/tts.py` e registre na fábrica `make_tts`.
- **Ações no PC (abrir programa, ligar luz):** isso é a **Frente B** e vive no
  *cérebro* (`jarvis/brain.py`, em `CLIENT_TOOLS`/`_execute_tool`). A voz herda de
  graça — qualquer ferramenta nova já funciona por voz, sem mudar nada aqui.

## Solução de problemas

- **"PIPER_MODEL não encontrado":** confira o caminho e se o `.onnx.json` está junto.
- **Sem áudio / erro de PortAudio:** instale as libs de sistema da seção 1 e confira
  `VOICE_MIC_DEVICE`.
- **"Não consegui falar com o cérebro":** o servidor está ligado? `JARVIS_BRAIN_URL`
  e `JARVIS_API_TOKEN` batem com o servidor? Teste:
  `curl http://localhost:8787/health`.
```
