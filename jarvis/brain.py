"""O cérebro do Jarvis: junta Claude, busca na web, memória e ferramentas.

Ferramentas client-side ativas:
- controlar_ar: liga/desliga, temperatura, modo e ventilação do ar-condicionado.
- controlar_tv: liga/desliga, volume, canais e teclas da TV.
Ambas passam pelo subsistema Tuya (jarvis/tuya_client.py), configurado via .env.

Modos de conversa:
- chat():        resposta completa de uma vez (Telegram e reserva).
- chat_stream(): transmite o texto em pedaços para a voz começar a falar antes.
"""
from __future__ import annotations

import logging
from typing import Any, Iterator

from anthropic import Anthropic

from .config import Settings
from .memory import Memory
from .personality import build_system_prompt
from .tuya_client import TuyaControl, load_tuya_config

log = logging.getLogger("jarvis.brain")

# Campos que o SDK injeta nos blocos mas que a API rejeita quando reenviados.
# Adicione aqui qualquer outro campo que apareça em "Extra inputs are not permitted".
_DROP: frozenset[str] = frozenset({"parsed_output"})

# Ferramentas client-side que VOCÊ executa (a busca na web é server-side e roda
# automaticamente do lado da Anthropic, então não entra aqui).
CLIENT_TOOLS: list[dict[str, Any]] = [
    {
        "name": "controlar_ar",
        "description": (
            "Controla o ar-condicionado da casa (via Smart IR). Use quando o usuário "
            "pedir para ligar ou desligar o ar, mudar a temperatura, o modo ou a "
            "ventilação — inclusive quando ele reclamar de calor ou frio. Se houver "
            "mais de um cômodo e o usuário não disser qual, pergunte antes de agir."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "comodo": {
                    "type": "string",
                    "description": "Cômodo do ar, ex.: 'sala' ou 'quarto'. Omita se o usuário não especificou.",
                },
                "acao": {
                    "type": "string",
                    "enum": ["ligar", "desligar", "temperatura", "modo", "ventilador"],
                },
                "valor": {
                    "type": "integer",
                    "description": "Para 'temperatura': graus de 16 a 30. Para 'modo': 0 a 4. Para 'ventilador': 0 a 3. Ignorado em ligar/desligar.",
                },
            },
            "required": ["acao"],
        },
    },
    {
        "name": "controlar_tv",
        "description": (
            "Controla a TV da casa (via Smart IR). Use para ligar/desligar ('power' "
            "alterna o estado), volume, troca de canal e teclas de navegação. Se houver "
            "mais de uma TV e o usuário não disser qual, pergunte antes de agir."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "comodo": {
                    "type": "string",
                    "description": "Cômodo da TV, ex.: 'sala' ou 'quarto'. Omita se não especificado.",
                },
                "acao": {
                    "type": "string",
                    "enum": [
                        "power", "volume_subir", "volume_baixar",
                        "canal_subir", "canal_baixar", "ir_para_canal", "tecla",
                    ],
                },
                "valor": {
                    "type": "string",
                    "description": "Para 'ir_para_canal': o número do canal. Para 'tecla': o nome (ok, menu, home, voltar, cima, baixo, esquerda, direita). Ignorado nas demais ações.",
                },
            },
            "required": ["acao"],
        },
    },
]


class Brain:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._client = Anthropic(api_key=settings.anthropic_api_key)
        self._memory = Memory(settings.db_path)
        self._system = build_system_prompt(
            settings.jarvis_name, settings.user_name
        )
        self._tuya: TuyaControl | None = None
        self._tuya_ready = False

    def _tools(self) -> list[dict[str, Any]]:
        web_search = {
            "type": "web_search_20250305",
            "name": "web_search",
            "max_uses": self._settings.web_search_max_uses,
        }
        return [web_search, *CLIENT_TOOLS]

    def _tuya_control(self) -> TuyaControl | None:
        """Cria o controle Tuya sob demanda. Devolve None se não estiver configurado."""
        if self._tuya_ready:
            return self._tuya
        self._tuya_ready = True
        config = load_tuya_config()
        if not config.configured:
            log.info("Tuya não configurada (.env sem TUYA_ACCESS_ID/SECRET).")
            self._tuya = None
        else:
            self._tuya = TuyaControl(config)
        return self._tuya

    def _execute_tool(self, name: str, tool_input: dict[str, Any]) -> str:
        """Executa uma ferramenta client-side."""
        if name in ("controlar_ar", "controlar_tv"):
            tuya = self._tuya_control()
            if tuya is None:
                return "O controle da casa ainda não está configurado (faltam as chaves Tuya no .env)."
            try:
                if name == "controlar_ar":
                    return tuya.ar(
                        tool_input.get("acao", ""),
                        tool_input.get("valor"),
                        tool_input.get("comodo"),
                    )
                return tuya.tv(
                    tool_input.get("acao", ""),
                    tool_input.get("valor"),
                    tool_input.get("comodo"),
                )
            except Exception as exc:  # noqa: BLE001
                log.exception("Erro executando %s", name)
                return f"Tentei, mas algo falhou no controle da casa: {exc}"
        return f"Ferramenta '{name}' ainda não implementada."

    def chat(self, session_id: str, user_message: str) -> str:
        """Recebe uma mensagem do usuário e devolve a resposta do Jarvis."""
        self._memory.append(session_id, "user", user_message)
        messages = self._memory.history(session_id, limit=20)

        for _ in range(6):  # trava de segurança contra loop infinito
            response = self._client.messages.create(
                model=self._settings.model,
                max_tokens=self._settings.max_tokens,
                system=self._system,
                messages=messages,
                tools=self._tools(),
            )

            assistant_content = [
                {k: v for k, v in block.model_dump().items() if k not in _DROP}
                for block in response.content
            ]
            self._memory.append(session_id, "assistant", assistant_content)
            messages.append({"role": "assistant", "content": assistant_content})

            if response.stop_reason != "tool_use":
                return self._extract_text(response)

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

    def chat_stream(self, session_id: str, user_message: str) -> Iterator[str]:
        """Igual ao chat(), mas vai entregando o texto em pedaços (deltas)."""
        self._memory.append(session_id, "user", user_message)
        messages = self._memory.history(session_id, limit=20)

        for _ in range(6):
            with self._client.messages.stream(
                model=self._settings.model,
                max_tokens=self._settings.max_tokens,
                system=self._system,
                messages=messages,
                tools=self._tools(),
            ) as stream:
                for chunk in stream.text_stream:
                    if chunk:
                        yield chunk
                final = stream.get_final_message()

            assistant_content = [
                {k: v for k, v in block.model_dump().items() if k not in _DROP}
                for block in final.content
            ]
            self._memory.append(session_id, "assistant", assistant_content)
            messages.append({"role": "assistant", "content": assistant_content})

            if final.stop_reason != "tool_use":
                return

            tool_results: list[dict[str, Any]] = []
            for block in final.content:
                if getattr(block, "type", None) == "tool_use":
                    result = self._execute_tool(block.name, block.input)
                    tool_results.append({
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result,
                    })

            if not tool_results:
                return

            self._memory.append(session_id, "user", tool_results)
            messages.append({"role": "user", "content": tool_results})

    @staticmethod
    def _extract_text(response: Any) -> str:
        parts = [b.text for b in response.content if getattr(b, "type", None) == "text"]
        return "\n".join(parts).strip() or "..."

    def reset(self, session_id: str) -> None:
        self._memory.clear(session_id)
