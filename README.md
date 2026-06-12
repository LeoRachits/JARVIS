# Jarvis — assistente pessoal estilo Homem de Ferro

Cérebro central que conversa com contexto, lembra do que foi dito, pesquisa na web
e roda no PC e no celular ao mesmo tempo. Você liga o cérebro em um lugar (PC,
Raspberry Pi ou nuvem) e os "corpos" (terminal, navegador, Telegram) falam com ele.

## O que tem aqui

```
JARVIS/
├── jarvis/
│   ├── config.py        # configurações via .env
│   ├── personality.py   # o "jeito" do Jarvis (edite aqui pra mudar a vibe)
│   ├── memory.py        # memória persistente (SQLite)
│   ├── brain.py         # núcleo: Claude + busca web + ferramentas
│   └── server.py        # API HTTP (PC e celular conversam por aqui)
├── cli.py               # converse no terminal (teste rápido)
├── telegram_bot.py      # acesso pelo celular via Telegram
├── requirements.txt
└── .env.example
```

## Passo a passo

**1. Instale as dependências**
```bash
pip install -r requirements.txt
```

**2. Configure**
```bash
cp .env.example .env
# abra o .env e cole sua ANTHROPIC_API_KEY (pegue em console.anthropic.com)
```

**3. Teste no terminal**
```bash
python cli.py
```
Se ele responder e conseguir pesquisar algo atual na web, o cérebro está pronto.

**4. Ligue o servidor (para acesso externo)**
```bash
uvicorn jarvis.server:app --host 0.0.0.0 --port 8787
```
Teste:
```bash
curl -X POST http://localhost:8787/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "bom dia", "session_id": "pc"}'
```

**5. Celular via Telegram**
- Crie um bot com o @BotFather e cole o token em `TELEGRAM_TOKEN` no `.env`.
- Pegue seu id com o @userinfobot e coloque em `TELEGRAM_ALLOWED_USER_ID`.
- Rode: `python telegram_bot.py`

## Roteiro para virar o Jarvis "de verdade" (voz)

Este esqueleto já é o cérebro completo (texto + memória + web + ferramentas).
Os próximos blocos transformam em voz:

1. **Palavra de ativação** ("Jarvis") → openWakeWord ou Porcupine.
2. **Ouvir** (voz → texto) → Whisper local manda o texto para `/chat`.
3. **Falar** (texto → voz) → Piper (local/grátis) ou ElevenLabs (voz premium).
4. **Subir com o PC** → Agendador de Tarefas (Windows) ou serviço.

Cada bloco só precisa chamar o endpoint `/chat` que já existe aqui.

## Como dar superpoderes (ferramentas)

Em `jarvis/brain.py`, adicione um schema em `CLIENT_TOOLS` e a execução em
`_execute_tool`. Exemplos do que dá pra fazer: abrir programas, ler/escrever
arquivos, controlar luzes (Home Assistant), enviar e-mail. O Claude decide
sozinho quando usar cada ferramenta.

## Segurança

- **Sempre** defina `JARVIS_API_TOKEN` e `TELEGRAM_ALLOWED_USER_ID` antes de
  expor o servidor para fora da sua rede.
- Nunca comite o arquivo `.env` (ele tem sua chave de API).
- O custo principal é o uso da API do Claude (barato para uso pessoal). Use
  `claude-haiku-4-5` no `.env` para reduzir custo e ganhar velocidade.
