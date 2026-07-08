"""O cérebro do Jarvis: junta DeepSeek/Claude, busca na web, memória e ferramentas.

Modelo padrão = DeepSeek (barato). Por comando de voz ("usa o Claude") a sessão
troca para o Claude, e ("volta pro DeepSeek") retorna. A pesquisa na web continua
funcionando mesmo no DeepSeek: quando ele precisa de informação atual, o cérebro
"empresta" a busca do Claude só naquele momento e devolve o resultado pro DeepSeek.

Como estender com suas próprias ferramentas (ex.: abrir programa, ligar luz):
1. Crie uma função e adicione um schema em CLIENT_TOOLS.
2. Registre a execução em self._execute_tool.
O loop de tool-use já chama suas funções automaticamente, em qualquer provedor.
"""
from __future__ import annotations

import logging
import unicodedata
from typing import Any

from .config import Settings
from .memory import Memory
from .personality import build_system_prompt
from .providers import PROVIDER_DEEPSEEK, ClientFactory, provider_of

logger = logging.getLogger("jarvis.brain")

# Ferramentas client-side que VOCÊ executa (abrir programa, casa inteligente, etc.).
# A busca na web NÃO entra aqui: no Claude ela é server-side; no DeepSeek o cérebro
# resolve sozinho (ver _SEARCH_TOOL e _web_search abaixo).
CLIENT_TOOLS: list[dict[str, Any]] = [
    # Exemplo pronto para você ativar depois:
    # {
    #     "name": "abrir_programa",
    #     "description": "Abre um programa no computador do usuário pelo nome.",
    #     "input_schema": {
    #         "type": "object",
    #         "properties": {"nome": {"type": "string"}},
    #         "required": ["nome"],
    #     },
    # },
]

# Ferramenta que o DeepSeek pode chamar quando precisar de informação atual.
# Quem executa de fato é o cérebro, usando a busca da Anthropic (ver _web_search).
_SEARCH_TOOL_NAME = "buscar_na_web"
_SEARCH_TOOL: dict[str, Any] = {
    "name": _SEARCH_TOOL_NAME,
    "description": (
        "Pesquisa informações ATUAIS na internet (notícias de hoje, cotações, "
        "placares, datas, fatos recentes, qualquer coisa que pode ter mudado). "
        "Use SEMPRE que a resposta depender de algo atual e você não tiver certeza. "
        "Passe a consulta em linguagem natural."
    ),
    "input_schema": {
        "type": "object",
        "properties": {
            "consulta": {
                "type": "string",
                "description": "O que pesquisar, em português.",
            }
        },
        "required": ["consulta"],
    },
}


def _normalize(text: str) -> str:
    """Minúsculas, sem acentos e com espaços colapsados — para casar comandos."""
    nfkd = unicodedata.normalize("NFKD", text.lower())
    sem_acento = "".join(c for c in nfkd if not unicodedata.combining(c))
    return " ".join(sem_acento.split())


# Frases que trocam o modelo da sessão. Curtas e específicas para evitar engano.
_TO_CLAUDE = (
    "usa o claude", "usar o claude", "usa claude", "troca pro claude",
    "trocar pro claude", "muda pro claude", "modo claude", "ativa o claude",
    "usa o sonnet", "modo sonnet", "modo premium",
)
_TO_DEEPSEEK = (
    "volta pro deepseek", "usa o deepseek", "usa deepseek", "modo deepseek",
    "troca pro deepseek", "modo economico", "modo barato", "modo padrao",
)
_WHICH_MODEL = (
    "qual modelo", "que modelo", "qual o modelo", "qual ia voce",
    "que ia voce", "qual ia esta", "qual modelo voce",
)


class Brain:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._clients = ClientFactory(settings)
        self._memory = Memory(settings.db_path)
        self._system = build_system_prompt(settings.jarvis_name, settings.user_name)
        # Preferência de modelo por sessão (em memória). Reinício volta ao padrão
        # (DeepSeek), que é justamente o comportamento desejado.
        self._session_model: dict[str, str] = {}

    # ------------------------------------------------------------------ #
    # API pública
    # ------------------------------------------------------------------ #
    def chat(self, session_id: str, user_message: str) -> str:
        """Recebe uma mensagem do usuário e devolve a resposta do Jarvis."""
        # 1) Comandos de troca de modelo são interceptados antes de gastar API.
        command_reply = self._handle_model_command(session_id, user_message)
        if command_reply is not None:
            return command_reply

        # 2) Modelo da sessão (padrão = DeepSeek).
        model = self._session_model.get(session_id, self._settings.default_model)
        provider = provider_of(model)

        self._memory.append(session_id, "user", user_message)
        messages = self._seed_messages(session_id)

        try:
            client = self._clients.for_model(model)
        except Exception:  # chave ausente / config — não derruba o servidor
            logger.exception("Falha ao obter client para o modelo %s", model)
            return "Não consegui acessar o modelo agora. Verifique a configuração."

        tools = self._tools_for(provider)

        # 3) Loop de tool-use: roda até o modelo parar de pedir ferramentas.
        for _ in range(self._settings.tool_loop_limit):
            try:
                response = client.messages.create(
                    model=model,
                    max_tokens=self._settings.max_tokens,
                    system=self._system,
                    messages=messages,
                    tools=tools,
                )
            except Exception:
                logger.exception("Erro chamando %s (%s)", model, provider)
                return (
                    "Tive um problema para pensar agora. "
                    "Pode repetir daqui a pouco?"
                )

            assistant_content = [b.model_dump() for b in response.content]
            self._memory.append(session_id, "assistant", assistant_content)
            messages.append({"role": "assistant", "content": assistant_content})

            if response.stop_reason != "tool_use":
                return self._extract_text(response)

            tool_results = self._run_tools(response)
            if not tool_results:
                return self._extract_text(response)

            self._memory.append(session_id, "user", tool_results)
            messages.append({"role": "user", "content": tool_results})

        return "Desculpe, me perdi processando isso. Pode reformular?"

    def reset(self, session_id: str) -> None:
        self._memory.clear(session_id)
        self._session_model.pop(session_id, None)

    def current_model(self, session_id: str) -> str:
        return self._session_model.get(session_id, self._settings.default_model)

    # ------------------------------------------------------------------ #
    # Comandos de modelo
    # ------------------------------------------------------------------ #
    def _handle_model_command(self, session_id: str, text: str) -> str | None:
        norm = _normalize(text)
        if len(norm) > 60:  # frases longas não são comandos
            return None

        if any(p in norm for p in _TO_CLAUDE):
            self._session_model[session_id] = self._settings.claude_model
            return f"Trocando para o {self._friendly(self._settings.claude_model)}, {self._settings.user_name}."

        if any(p in norm for p in _TO_DEEPSEEK):
            self._session_model[session_id] = self._settings.default_model
            return f"Voltando para o {self._friendly(self._settings.default_model)}, modo econômico."

        if any(p in norm for p in _WHICH_MODEL):
            return f"No momento estou usando o {self._friendly(self.current_model(session_id))}."

        return None

    @staticmethod
    def _friendly(model: str) -> str:
        low = model.lower()
        if low.startswith("deepseek"):
            return "DeepSeek"
        if "sonnet" in low:
            return "Claude Sonnet"
        if "haiku" in low:
            return "Claude Haiku"
        if "opus" in low:
            return "Claude Opus"
        return "Claude"

    # ------------------------------------------------------------------ #
    # Ferramentas
    # ------------------------------------------------------------------ #
    def _tools_for(self, provider: str) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        if self._settings.enable_web_search:
            if provider == PROVIDER_DEEPSEEK:
                # DeepSeek não tem busca nativa: damos a ferramenta que o cérebro executa.
                tools.append(_SEARCH_TOOL)
            else:
                # Claude usa a busca server-side da Anthropic.
                tools.append({
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": self._settings.web_search_max_uses,
                })
        tools.extend(CLIENT_TOOLS)
        return tools

    def _run_tools(self, response: Any) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for block in response.content:
            if getattr(block, "type", None) != "tool_use":
                continue
            if block.name == _SEARCH_TOOL_NAME:
                consulta = (block.input or {}).get("consulta", "")
                content = self._web_search(consulta)
            else:
                content = self._execute_tool(block.name, block.input or {})
            results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": content,
            })
        return results

    def _execute_tool(self, name: str, tool_input: dict[str, Any]) -> str:
        """Executa uma ferramenta client-side. Adicione as suas aqui."""
        # if name == "abrir_programa":
        #     return abrir_programa(tool_input["nome"])
        return f"Ferramenta '{name}' ainda não implementada."

    def _web_search(self, consulta: str) -> str:
        """Busca emprestada: usa a pesquisa do Claude e devolve o texto sintetizado.

        Roda mesmo quando a sessão está no DeepSeek — é o que mantém a pesquisa na
        web viva sem precisar de busca nativa do DeepSeek.
        """
        consulta = (consulta or "").strip()
        if not consulta:
            return "Consulta vazia."
        if not self._settings.anthropic_api_key:
            return "Busca na web indisponível: falta a chave da Anthropic."
        try:
            client = self._clients.for_model(self._settings.search_model)
            resp = client.messages.create(
                model=self._settings.search_model,
                max_tokens=self._settings.max_tokens,
                system=(
                    "Você é um buscador. Pesquise na web e responda em português, "
                    "de forma direta e factual, com a informação mais atual. "
                    "Não adicione opinião nem saudação."
                ),
                messages=[{"role": "user", "content": consulta}],
                tools=[{
                    "type": "web_search_20250305",
                    "name": "web_search",
                    "max_uses": self._settings.web_search_max_uses,
                }],
            )
            texto = self._extract_text(resp)
            return texto or "Não encontrei nada relevante."
        except Exception:
            logger.exception("Falha na busca emprestada para: %s", consulta)
            return "Não consegui pesquisar agora. Tente novamente em instantes."

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _seed_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Carrega o histórico já achatado em texto.

        Achatar evita dois problemas: (1) reenviar blocos de ferramenta de um
        provedor para o outro ao trocar de modelo no meio da conversa, e
        (2) qualquer formato exótico atravancar a próxima chamada. O registro
        completo continua salvo na memória; aqui só montamos o contexto da chamada.
        """
        raw = self._memory.history(session_id, limit=20)
        out: list[dict[str, Any]] = []
        for m in raw:
            text = self._content_to_text(m["content"])
            if text:
                out.append({"role": m["role"], "content": text})
        return out

    @staticmethod
    def _content_to_text(content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for block in content:
                if not isinstance(block, dict):
                    continue
                btype = block.get("type")
                if btype == "text" and block.get("text"):
                    parts.append(str(block["text"]))
                elif btype == "tool_result":
                    inner = block.get("content")
                    if isinstance(inner, str):
                        parts.append(inner)
                    elif isinstance(inner, list):
                        for b in inner:
                            if isinstance(b, dict) and b.get("type") == "text":
                                parts.append(str(b.get("text", "")))
            return "\n".join(p for p in parts if p).strip()
        return ""

    @staticmethod
    def _extract_text(response: Any) -> str:
        parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
        return "\n".join(parts).strip() or "..."
