# SETUP-WINDOWS.md — Runbook para o agente executar (VS Code / Windows)

> **Para o agente (Sonnet) que vai executar:** siga este runbook **na ordem**, de cima
> para baixo. Rode os comandos no terminal integrado do VS Code (PowerShell). **Não pule
> as travas (STOP).** Em cada fase há um teste; só avance se ele passar. Se um comando
> falhar, mostre o erro, aplique o fix indicado e tente de novo — não siga adiante
> ignorando falha.

## Regras inegociáveis para o agente

1. **Nunca** escreva segredos (chave da API, tokens) em código ou em arquivos versionados.
   Segredos vão **só** no `.env`, preenchido pelo usuário.
2. **Nunca** comite o `.env`. Se não houver `.gitignore`, crie um com `.env` e `.venv/`.
3. O caminho do projeto tem espaço (`jarvis voz`) — **sempre** use aspas em comandos.
4. Comandos longos/servidores: rode em terminal separado ou em background, conforme indicado.
5. Onde estiver escrito **STOP**, pare e peça a informação ao usuário antes de continuar.

---

## FASE 0 — Conferir ambiente e estrutura

**0.1** Confirme o diretório e o Python:

```powershell
cd "C:\dev\pessoal\JARVIS\jarvis voz"
py -0p
python --version
```

- Preferência: **Python 3.11**. Se só houver 3.12/3.13, pode seguir, mas anote: o
  `webrtcvad` talvez precise do pacote alternativo `webrtcvad-wheels` (tratado na Fase 2).

**0.2** Verifique a estrutura da pasta:

```powershell
dir
dir jarvis
dir voice
```

A pasta **precisa** conter:
- `jarvis\` com: `config.py`, `brain.py`, `memory.py`, `personality.py`, `server.py`, `__init__.py`
- `voice\` com: `config.py`, `audio.py`, `wakeword.py`, `recorder.py`, `stt.py`, `tts.py`, `brain_client.py`, `assistant.py`, `__init__.py`
- na raiz: `cli.py`, `voice_run.py`, `requirements.txt`, `requirements-voice.txt`, `env.example`, `voice.env.example`

> **STOP (se faltar o cérebro):** se a pasta `jarvis\` não existir ou estiver incompleta,
> **pare** e avise o usuário: "Faltam os arquivos do cérebro. Baixe `config.py`,
> `brain.py`, `memory.py`, `personality.py`, `server.py` do seu Projeto no Claude e
> coloque-os dentro de uma pasta `jarvis\`. Sem o cérebro, a voz não funciona."
> Não tente inventar/recriar esses arquivos.

---

## FASE 1 — Ligar e validar o CÉREBRO (sem voz)

**1.1** Criar e ativar o ambiente virtual:

```powershell
py -3.11 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

> Se a ativação falhar com "execução de scripts desabilitada", rode uma vez e ative de novo:
> ```powershell
> Set-ExecutionPolicy -Scope CurrentUser -ExecutionPolicy RemoteSigned
> ```
> (Se `py -3.11` não existir, use `py -3 -m venv .venv`.)

**1.2** Instalar dependências do cérebro:

```powershell
python -m pip install --upgrade pip
pip install -r requirements.txt
```

**1.3** Garantir o `.env`:

```powershell
if (-not (Test-Path .env)) { Copy-Item env.example .env }
```

**1.4** Garantir `.gitignore`:

```powershell
if (-not (Test-Path .gitignore)) { Set-Content .gitignore ".env`n.venv/`njarvis_memory.db`nvoices/" }
```

**1.5** Conferir se a chave da API foi preenchida:

```powershell
Select-String -Path .env -Pattern "^ANTHROPIC_API_KEY="
```

> **STOP (chave da API):** se o valor estiver vazio ou ainda for
> `coloque_sua_chave_aqui`, **pare** e peça ao usuário: "Abra o `.env` e cole sua chave
> em `ANTHROPIC_API_KEY=` (pegue em console.anthropic.com). Me avise quando salvar."
> Não invente nem peça a chave em texto no chat — ela deve ser digitada no arquivo.

**1.6** Teste de fogo do cérebro (uma única chamada, não interativa):

```powershell
python -c "from jarvis.config import load_settings; from jarvis.brain import Brain; print(Brain(load_settings()).chat('smoke','Responda apenas: cerebro online.'))"
```

- **Esperado:** ele imprime algo como `cerebro online.` (ou similar).
- Erros comuns:
  - `ANTHROPIC_API_KEY ... ausente` → volte ao passo 1.5 (chave não salva).
  - Erro de autenticação 401 da Anthropic → chave inválida; peça a chave correta ao usuário.
  - `ModuleNotFoundError` → o venv não está ativo ou faltou `pip install -r requirements.txt`.

**1.7 (opcional, confirma a busca web):**

```powershell
python -c "from jarvis.config import load_settings; from jarvis.brain import Brain; print(Brain(load_settings()).chat('smoke','Qual a data de hoje e uma manchete de hoje?'))"
```

> **TRAVA DE FASE:** só avance para a FASE 2 se o passo **1.6** imprimiu uma resposta.
> O usuário também pode conversar manualmente com `python cli.py` (Ctrl+C para sair).

---

## FASE 2 — Adicionar a VOZ (só após a Fase 1 passar)

### 2.1 Subir o servidor do cérebro (a voz fala com ele por HTTP)

Inicie o servidor em background e valide o `/health`:

```powershell
Start-Process -FilePath ".\.venv\Scripts\python.exe" -ArgumentList "-m","uvicorn","jarvis.server:app","--host","127.0.0.1","--port","8787"
Start-Sleep -Seconds 4
Invoke-RestMethod http://127.0.0.1:8787/health
```

- **Esperado:** um JSON com `status = ok`.
- Para parar o servidor depois: `Get-Process python | Stop-Process` (cuidado: encerra todos
  os Python; em dúvida, feche pela aba do terminal/Processos).

### 2.2 Instalar dependências de voz

```powershell
pip install -r requirements-voice.txt
```

> Se `webrtcvad` falhar ao compilar (Windows sem Build Tools), troque pelo wheel pronto:
> ```powershell
> pip install webrtcvad-wheels
> ```
> (mesmo módulo `webrtcvad`, importa igual — o código não muda.)

### 2.3 Anexar a configuração de voz ao `.env`

Se ainda não houver as variáveis de voz no `.env`, anexe o exemplo e abra para ajustar:

```powershell
if (-not (Select-String -Path .env -Pattern "JARVIS_BRAIN_URL" -Quiet)) {
  Add-Content .env "`n"; Get-Content voice.env.example | Add-Content .env
}
notepad .env
```

No `.env`, garanta:
- `JARVIS_BRAIN_URL=http://127.0.0.1:8787`
- `JARVIS_API_TOKEN=` → **o mesmo** valor do servidor (se você definiu um token; se estiver
  vazio nos dois, ok para teste local).
- `VOICE_SESSION_ID=default` (memória compartilhada com Telegram/terminal).
- `TTS_ENGINE=piper` e `PIPER_MODEL=./voices/pt_BR-faber-medium.onnx` (baixado em 2.4).

### 2.4 Baixar a voz PT-BR do Piper

```powershell
New-Item -ItemType Directory -Force -Path voices | Out-Null
Invoke-WebRequest -Uri "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx" -OutFile "voices\pt_BR-faber-medium.onnx"
Invoke-WebRequest -Uri "https://huggingface.co/rhasspy/piper-voices/resolve/main/pt/pt_BR/faber/medium/pt_BR-faber-medium.onnx.json" -OutFile "voices\pt_BR-faber-medium.onnx.json"
```

(O `.onnx.json` precisa ficar ao lado do `.onnx`, mesmo nome.)

### 2.5 Garantir o binário do Piper

Primeiro tente o pacote pip (já vem em `requirements-voice.txt`):

```powershell
piper --help
```

- Se aparecer a ajuda do Piper, ótimo — `PIPER_BINARY=piper` funciona.
- **Se der "comando não encontrado" ou erro de fonemas/espeak**, baixe o binário standalone
  do Windows (mais confiável): vá às *releases* do projeto `rhasspy/piper` no GitHub, baixe
  o `.zip` do Windows (ex.: `piper_windows_amd64.zip`), extraia para `C:\dev\pessoal\JARVIS\piper\`
  e no `.env` aponte:
  ```
  PIPER_BINARY=C:\dev\pessoal\JARVIS\piper\piper.exe
  ```

> **Alternativa sem Piper:** se o Piper insistir em dar trabalho, use voz na nuvem.
> No `.env`: `TTS_ENGINE=elevenlabs`, e preencha `ELEVENLABS_API_KEY` e `ELEVENLABS_VOICE_ID`.
> Aí o Piper não é necessário. (ElevenLabs é pago.)

### 2.6 Conferir o microfone (opcional, recomendado)

```powershell
python -c "import sounddevice as sd; print(sd.query_devices())"
```

Se o microfone padrão não for o certo, anote o índice e coloque em `VOICE_MIC_DEVICE` no `.env`.

### 2.7 Rodar a voz

```powershell
python voice_run.py
```

- **Primeira execução baixa** os modelos do openWakeWord e do Whisper — pode levar 1–3 min.
- Quando aparecer "Jarvis de voz no ar", diga **"Hey Jarvis"**, espere o bip e fale.
- Ele transcreve, manda pro cérebro (que pode pesquisar na web) e responde **falando**.
- `Ctrl+C` encerra.

> **TRAVA DE FASE:** o teste passou se, ao dizer "Hey Jarvis" e fazer uma pergunta, o
> Jarvis responder por voz. Se ele disser "Não consegui falar com o cérebro", o servidor
> da 2.1 caiu ou `JARVIS_BRAIN_URL`/`JARVIS_API_TOKEN` não batem — revise 2.1 e 2.3.

---

## Ajustes finos (se precisar)

- **Disparo falso da palavra de ativação** → suba `WAKEWORD_THRESHOLD` para `0.6`.
- **Corta a fala cedo demais** → aumente `VAD_SILENCE_MS` (ex.: `1000`–`1200`).
- **Transcrição ruim/lenta** → ajuste `WHISPER_MODEL` (`base` mais rápido, `medium` melhor);
  com GPU NVIDIA: `WHISPER_DEVICE=cuda` e `WHISPER_COMPUTE_TYPE=float16`.
- **Sem áudio** → confira `VOICE_MIC_DEVICE` e se o alto-falante padrão está certo.

## Resumo do que cada fase entrega

- **Fase 1:** cérebro vivo, validado com a chave real (resolve a pendência do CHECKPOINT).
- **Fase 2:** o cérebro virou o Jarvis de voz — ouve por "Hey Jarvis", pensa e fala.
