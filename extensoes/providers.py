"""ARQUIVO — Provedores de modelo (DeepSeek + Claude).

Este módulo foi removido do pacote jarvis/ quando o Jarvis passou a ser só-Claude
(SPEC-00). Está aqui como referência caso um segundo provedor seja reintroduzido.

Hoje o Jarvis usa um único client Anthropic, criado diretamente em jarvis/brain.py.
"""
from __future__ import annotations

from anthropic import Anthropic

from jarvis.config import Settings

PROVIDER_DEEPSEEK = "deepseek"
PROVIDER_ANTHROPIC = "anthropic"


def provider_of(model: str) -> str:
    """Descobre o provedor a partir do nome do modelo."""
    return PROVIDER_DEEPSEEK if model.lower().startswith("deepseek") else PROVIDER_ANTHROPIC


class ProviderError(RuntimeError):
    """Erro de configuração de provedor (ex.: chave ausente para o modelo pedido)."""


class ClientFactory:
    """Cria e mantém em cache um client por provedor.

    Mantém os clients vivos (conexões reaproveitadas) durante toda a execução do
    servidor — importante para um processo que roda 24h.
    """

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._cache: dict[str, Anthropic] = {}

    def for_model(self, model: str) -> Anthropic:
        provider = provider_of(model)
        if provider in self._cache:
            return self._cache[provider]
        client = self._build(provider)
        self._cache[provider] = client
        return client

    def _build(self, provider: str) -> Anthropic:
        s = self._settings
        if provider == PROVIDER_DEEPSEEK:
            deepseek_api_key = getattr(s, "deepseek_api_key", "")
            deepseek_base_url = getattr(s, "deepseek_base_url", "https://api.deepseek.com/anthropic")
            if not deepseek_api_key:
                raise ProviderError(
                    "Modelo DeepSeek pedido, mas DEEPSEEK_API_KEY não está no .env."
                )
            return Anthropic(
                api_key=deepseek_api_key,
                base_url=deepseek_base_url,
                timeout=s.request_timeout,
                max_retries=s.max_retries,
            )

        if not s.anthropic_api_key:
            raise ProviderError(
                "Modelo Claude pedido, mas ANTHROPIC_API_KEY não está no .env."
            )
        return Anthropic(
            api_key=s.anthropic_api_key,
            timeout=s.request_timeout,
            max_retries=s.max_retries,
        )
