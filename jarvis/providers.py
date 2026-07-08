"""Provedores de modelo: decide qual API atende cada modelo e cria o client certo.

Hoje o Jarvis fala com dois provedores, ambos pelo MESMO SDK (anthropic):
  - Claude  -> API oficial da Anthropic.
  - DeepSeek -> endpoint compatível com Anthropic (https://api.deepseek.com/anthropic),
                então reaproveitamos o mesmo client só trocando base_url + chave.

Regra de roteamento: o nome do modelo decide o provedor.
  - Começa com "deepseek"  -> DeepSeek.
  - Qualquer outra coisa    -> Anthropic (Claude).

Ponto de extensão: para plugar um terceiro provedor (ex.: um modelo local com
endpoint compatível), basta adicionar um ramo em `provider_of` e em `make_client`.
"""
from __future__ import annotations

from functools import lru_cache

from anthropic import Anthropic

from .config import Settings

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
            if not s.deepseek_api_key:
                raise ProviderError(
                    "Modelo DeepSeek pedido, mas DEEPSEEK_API_KEY não está no .env. "
                    "Pegue uma chave em platform.deepseek.com."
                )
            return Anthropic(
                api_key=s.deepseek_api_key,
                base_url=s.deepseek_base_url,
                timeout=s.request_timeout,
                max_retries=s.max_retries,
            )

        # Anthropic (Claude) — provedor padrão.
        if not s.anthropic_api_key:
            raise ProviderError(
                "Modelo Claude pedido (ou busca na web acionada), mas "
                "ANTHROPIC_API_KEY não está no .env."
            )
        return Anthropic(
            api_key=s.anthropic_api_key,
            timeout=s.request_timeout,
            max_retries=s.max_retries,
        )
