"""O cérebro do Jarvis: junta Claude, busca na web, memória e ferramentas.

Como estender com suas próprias ferramentas (ex.: abrir programa, ligar luz):
1. Crie uma função e adicione um schema em CLIENT_TOOLS.
2. Registre a execução em self._execute_tool.
O loop de tool-use já está pronto para chamar suas funções automaticamente.

Robustez:
- Toda chamada à API tem timeout e retries (configuráveis no .env).
- Erros de rede/API viram resposta amigável + log, nunca derrubam o processo.
- Só o TEXTO final entra na memória; blocos de busca web/ferramenta ficam apenas
  no fluxo do turno atual (não são reenviados depois — evita erro e gasta menos).
"""
from __future__ import annotations

import logging
import time
from typing import Any

from anthropic import (
    Anthropic,
    APIConnectionError,
    APIError,
    APIStatusError,
    RateLimitError,
)

from .config import Settings
from .memory import Memory
from .personality import build_system_prompt

logger = logging.getLogger(__name__)

# Trava de segurança: máximo de idas e vindas com ferramentas num único turno.
MAX_TOOL_ITERATIONS = 6

# Tamanho do trecho da mensagem que aparece no log (evita poluir).
_LOG_PREVIEW = 120

# Ferramentas client-side que VOCÊ executa (a busca na web é server-side e
# roda automaticamente do lado da Anthropic, então não entra aqui).
CLIENT_TOOLS: list[dict[str, Any]] = [
    # Exemplo pronto para você ativar na Frente B:
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


def _preview(text: str) -> str:
    text = text.replace("\n", " ").strip()
    return text if len(text) <= _LOG_PREVIEW else text[:_LOG_PREVIEW] + "…"


class Brain:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = Anthropic(
            api_key=settings.anthropic_api_key,
            timeout=settings.request_timeout,
            max_retries=settings.max_retries,
        )
        self._memory = Memory(settings.db_path)
        self._system = build_system_prompt(
            settings.jarvis_name, settings.user_name
        )
        logger.info(
            "Brain iniciado (modelo=%s, timeout=%ss, max_retries=%s).",
            settings.model, settings.request_timeout, settings.max_retries,
        )

    def _tools(self) -> list[dict[str, Any]]:
        web_search = {
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": self._settings.web_search_max_uses,
        }
        return [web_search, *CLIENT_TOOLS]

    def _execute_tool(self, name: str, tool_input: dict[str, Any]) -> str:
        """Executa uma ferramenta client-side. Adicione as suas aqui.

        Erro de ferramenta vira resultado de texto e volta para o modelo —
        nunca derruba o processo (falha de ferramenta é estado esperado).
        """
        try:
            # if name == "abrir_programa":
            #     return abrir_programa(tool_input["nome"])
            logger.warning("Ferramenta não implementada chamada: %s", name)
            return f"Ferramenta '{name}' ainda não implementada."
        except Exception as exc:  # noqa: BLE001 - blindar o loop de propósito
            logger.exception("Erro ao executar ferramenta %s: %s", name, exc)
            return f"Erro ao executar a ferramenta '{name}': {exc}"

    def chat(self, session_id: str, user_message: str) -> str:
        """Recebe uma mensagem do usuário e devolve a resposta do Jarvis."""
        started = time.monotonic()
        logger.info("[%s] Usuário: %s", session_id, _preview(user_message))

        self._memory.append(session_id, "user", user_message)
        messages = self._memory.history(session_id, limit=20)

        try:
            return self._run_loop(session_id, messages, started)
        except RateLimitError:
            logger.warning("[%s] Rate limit da API atingido.", session_id)
            return "Estou recebendo pedidos demais agora, Senhor. Tente de novo em instantes."
        except APIConnectionError as exc:
            logger.error("[%s] Falha de conexão com a API: %s", session_id, exc)
            return "Não consegui falar com meus servidores — parece problema de conexão. Tente de novo."
        except APIStatusError as exc:
            logger.error(
                "[%s] Erro de status da API (%s): %s", session_id, exc.status_code, exc
            )
            if exc.status_code == 401:
                return "Minha chave de acesso foi recusada. Verifique a ANTHROPIC_API_KEY no .env, Senhor."
            if exc.status_code == 400:
                return "Houve um problema com o formato do pedido. Tente reformular, por favor."
            return "Meus servidores responderam com um erro. Tente novamente em instantes."
        except APIError as exc:
            logger.exception("[%s] Erro inesperado da API: %s", session_id, exc)
            return "Tive um problema inesperado ao processar isso. Tente de novo, Senhor."
        except Exception as exc:  # noqa: BLE001 - blindagem final do turno
            logger.exception("[%s] Erro não tratado: %s", session_id, exc)
            return "Desculpe, algo deu errado aqui. Tente novamente."

    def _run_loop(
        self, session_id: str, messages: list[dict[str, Any]], started: float
    ) -> str:
        for iteration in range(MAX_TOOL_ITERATIONS):
            response = self._client.messages.create(
                model=self._settings.model,
                max_tokens=self._settings.max_tokens,
                system=self._system,
                messages=messages,
                tools=self._tools(),
            )
            self._log_usage(session_id, response, iteration)

            # Blocos completos só no fluxo deste turno (a API exige o par
            # tool_use/tool_result); NÃO são persistidos na memória.
            assistant_blocks = [block.model_dump() for block in response.content]
            messages.append({"role": "assistant", "content": assistant_blocks})

            if response.stop_reason != "tool_use":
                return self._finish(session_id, response, started)

            tool_results = self._collect_tool_results(response)
            if not tool_results:
                return self._finish(session_id, response, started)

            messages.append({"role": "user", "content": tool_results})

        logger.warning(
            "[%s] Loop de ferramentas esgotou %s iterações.",
            session_id, MAX_TOOL_ITERATIONS,
        )
        fallback = "Desculpe, me perdi processando isso. Pode reformular?"
        self._memory.append(session_id, "assistant", fallback)
        return fallback

    def _collect_tool_results(self, response: Any) -> list[dict[str, Any]]:
        results: list[dict[str, Any]] = []
        for block in response.content:
            if getattr(block, "type", None) == "tool_use":
                logger.info("Executando ferramenta: %s", block.name)
                output = self._execute_tool(block.name, block.input)
                results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": output,
                })
        return results

    def _finish(self, session_id: str, response: Any, started: float) -> str:
        text = self._extract_text(response)
        self._memory.append(session_id, "assistant", text)
        elapsed = time.monotonic() - started
        used_web = any(
            getattr(b, "type", None) == "web_search_tool_result"
            for b in response.content
        )
        logger.info(
            "[%s] Jarvis (%.1fs%s): %s",
            session_id, elapsed, ", web" if used_web else "", _preview(text),
        )
        return text

    @staticmethod
    def _log_usage(session_id: str, response: Any, iteration: int) -> None:
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        logger.debug(
            "[%s] iter=%s tokens_in=%s tokens_out=%s stop=%s",
            session_id, iteration,
            getattr(usage, "input_tokens", "?"),
            getattr(usage, "output_tokens", "?"),
            getattr(response, "stop_reason", "?"),
        )

    @staticmethod
    def _extract_text(response: Any) -> str:
        parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
        return "\n".join(parts).strip() or "..."

    def reset(self, session_id: str) -> None:
        logger.info("[%s] Memória limpa.", session_id)
        self._memory.clear(session_id)
