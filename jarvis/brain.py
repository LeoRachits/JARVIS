"""O cérebro do Jarvis: junta Claude, busca na web, memória e ferramentas.

Como estender com suas próprias ferramentas (ex.: abrir programa, ligar luz):
1. Crie uma função e adicione um schema em CLIENT_TOOLS.
2. Registre a execução em self._execute_tool.
O loop de tool-use já está pronto para chamar suas funções automaticamente.
"""
from __future__ import annotations

from typing import Any

from anthropic import Anthropic

from .config import Settings
from .memory import Memory
from .personality import build_system_prompt

# Ferramentas client-side que VOCÊ executa (a busca na web é server-side e
# roda automaticamente do lado da Anthropic, então não entra aqui).
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
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._memory = Memory(settings.db_path)
        self._system = build_system_prompt(
            settings.jarvis_name, settings.user_name
        )

    def _tools(self) -> list[dict[str, Any]]:
        web_search = {
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": self._settings.web_search_max_uses,
        }
        return [web_search, *CLIENT_TOOLS]

    def _execute_tool(self, name: str, tool_input: dict[str, Any]) -> str:
        """Executa uma ferramenta client-side. Adicione as suas aqui."""
        # if name == "abrir_programa":
        #     return abrir_programa(tool_input["nome"])
        return f"Ferramenta '{name}' ainda não implementada."

    def chat(self, session_id: str, user_message: str) -> str:
        """Recebe uma mensagem do usuário e devolve a resposta do Jarvis."""
        self._memory.append(session_id, "user", user_message)
        messages = self._memory.history(session_id, limit=20)

        # Loop de tool-use: roda até o modelo parar de pedir ferramentas.
        for _ in range(6):  # trava de segurança contra loop infinito
            response = self._client.messages.create(
                model=self._settings.model,
                max_tokens=self._settings.max_tokens,
                system=self._system,
                messages=messages,
                tools=self._tools(),
            )

            assistant_content = [block.model_dump() for block in response.content]
            self._memory.append(session_id, "assistant", assistant_content)
            messages.append({"role": "assistant", "content": assistant_content})

            if response.stop_reason != "tool_use":
                return self._extract_text(response)

            # Executa as ferramentas client-side que o modelo pediu.
            tool_results: list[dict[str, Any]] = []
            for block in response.content:
                if block.type == "tool_use":
                    result = self._execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            if not tool_results:
                return self._extract_text(response)

            self._memory.append(session_id, "user", tool_results)
            messages.append({"role": "user", "content": tool_results})

        return "Desculpe, me perdi processando isso. Pode reformular?"

    @staticmethod
    def _extract_text(response: Any) -> str:
        parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
        return "\n".join(parts).strip() or "..."

    def reset(self, session_id: str) -> None:
        self._memory.clear(session_id)
