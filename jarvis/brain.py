"""O cérebro do Jarvis: Claude, busca na web nativa, memória e ferramentas.

Modelo fixo: claude-sonnet-4-6 (configurável via JARVIS_MODEL no .env).
A busca na web usa a ferramenta server-side nativa da Anthropic (web_search_20250305) —
sem intermediários, sem "busca emprestada".

Como estender com suas próprias ferramentas (ex.: abrir programa, ligar luz):
1. Crie uma função e adicione um schema em CLIENT_TOOLS.
2. Registre a execução em self._execute_tool.
O loop de tool-use já chama suas funções automaticamente.
"""
from __future__ import annotations

import logging
from typing import Any, Iterator

from anthropic import Anthropic

from .config import Settings
from .memory import Memory
from .personality import build_system_prompt

logger = logging.getLogger("jarvis.brain")

# Ferramentas client-side que VOCÊ executa (abrir programa, casa inteligente, etc.).
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


class Brain:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = Anthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.request_timeout,
            max_retries=settings.max_retries,
        )
        self._memory = Memory(settings.db_path)
        self._system = build_system_prompt(settings.jarvis_name, settings.user_name)

    # ------------------------------------------------------------------ #
    # API pública
    # ------------------------------------------------------------------ #
    def chat(
        self,
        session_id: str,
        user_message: str,
        images: list[dict[str, Any]] | None = None,
    ) -> str:
        """Recebe uma mensagem do usuário e devolve a resposta do Jarvis."""
        model = self._settings.model

        self._memory.append(session_id, "user", user_message)
        messages = self._seed_messages(session_id)

        # Substitui a última mensagem pelo conteúdo rico quando há imagens.
        if images and messages and messages[-1]["role"] == "user":
            messages[-1]["content"] = [
                *images,
                {"type": "text", "text": user_message},
            ]

        tools = self._tools_for()

        # Loop de tool-use: roda até o modelo parar de pedir ferramentas.
        for _ in range(self._settings.tool_loop_limit):
            try:
                response = self._client.messages.create(
                    model=model,
                    max_tokens=self._settings.max_tokens,
                    system=self._system,
                    messages=messages,
                    tools=tools,
                )
            except Exception:
                logger.exception("Erro chamando %s", model)
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

    def chat_stream(self, session_id: str, user_message: str) -> Iterator[dict]:
        """Versão streaming do chat(): faz yield de eventos em vez de return.

        Formatos de evento:
          {"type": "state",  "state": "thinking"}
          {"type": "state",  "state": "tool", "name": "<ferramenta>"}
          {"type": "delta",  "text": "<chunk>"}
          {"type": "done",   "reply": "<texto completo>"}
          {"type": "error",  "message": "<mensagem>"}
        """
        yield {"type": "state", "state": "thinking"}

        model = self._settings.model
        self._memory.append(session_id, "user", user_message)
        messages = self._seed_messages(session_id)
        tools = self._tools_for()
        full_reply = ""

        try:
            for _ in range(self._settings.tool_loop_limit):
                accumulated: list[str] = []

                with self._client.messages.stream(
                    model=model,
                    max_tokens=self._settings.max_tokens,
                    system=self._system,
                    messages=messages,
                    tools=tools,
                ) as stream:
                    for text in stream.text_stream:
                        accumulated.append(text)
                        yield {"type": "delta", "text": text}
                    final = stream.get_final_message()

                full_reply = "".join(accumulated)
                assistant_content = [b.model_dump() for b in final.content]
                self._memory.append(session_id, "assistant", assistant_content)
                messages.append({"role": "assistant", "content": assistant_content})

                if final.stop_reason != "tool_use":
                    yield {"type": "done", "reply": full_reply}
                    return

                # Ferramentas client-side: emite state antes de executar cada uma.
                tool_results: list[dict[str, Any]] = []
                for block in final.content:
                    if getattr(block, "type", None) != "tool_use":
                        continue
                    yield {"type": "state", "state": "tool", "name": block.name}
                    content = self._execute_tool(block.name, block.input or {})
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": content,
                    })

                if not tool_results:
                    yield {"type": "done", "reply": full_reply}
                    return

                self._memory.append(session_id, "user", tool_results)
                messages.append({"role": "user", "content": tool_results})

            yield {"type": "done", "reply": full_reply or "Desculpe, me perdi processando isso. Pode reformular?"}

        except Exception:
            logger.exception("Erro no chat_stream (session=%s)", session_id)
            yield {"type": "error", "message": "Tive um problema para pensar agora. Pode repetir daqui a pouco?"}

    def reset(self, session_id: str) -> None:
        self._memory.clear(session_id)

    # ------------------------------------------------------------------ #
    # Ferramentas
    # ------------------------------------------------------------------ #
    def _tools_for(self) -> list[dict[str, Any]]:
        tools: list[dict[str, Any]] = []
        if self._settings.enable_web_search:
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

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #
    def _seed_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Carrega o histórico achatado em texto para compor o contexto da chamada."""
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
