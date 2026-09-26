"""Build the configured providers and a router from settings + app_settings."""

from typing import Any

from app.core.config import Settings
from app.llm.anthropic import AnthropicProvider
from app.llm.base import LLMProvider
from app.llm.circuit import CircuitBreaker
from app.llm.gemini import GeminiProvider
from app.llm.ollama import OllamaProvider
from app.llm.openai import OpenAIProvider
from app.llm.router import LLMRouter

KNOWN_PROVIDERS = ("openai", "anthropic", "gemini", "ollama")
DEFAULT_CHAIN = [*KNOWN_PROVIDERS, "rule_based"]


def build_providers(settings: Settings) -> dict[str, LLMProvider]:
    """Only providers with credentials (or a URL, for Ollama) exist at all."""
    providers: dict[str, LLMProvider] = {}
    if settings.anthropic_api_key:
        providers["anthropic"] = AnthropicProvider(
            settings.anthropic_api_key.get_secret_value(), settings.anthropic_model
        )
    if settings.openai_api_key:
        providers["openai"] = OpenAIProvider(
            settings.openai_api_key.get_secret_value(),
            settings.openai_model,
            reasoning_effort=settings.openai_reasoning_effort or None,
        )
    if settings.gemini_api_key:
        providers["gemini"] = GeminiProvider(
            settings.gemini_api_key.get_secret_value(), settings.gemini_model
        )
    if settings.ollama_base_url:
        providers["ollama"] = OllamaProvider(settings.ollama_base_url, settings.ollama_model)
    return providers


def build_router(
    providers: dict[str, LLMProvider],
    breaker: CircuitBreaker,
    chain: list[str],
    chaos: dict[str, Any],
    *,
    call_timeout_s: float = 30.0,
    budget_s: float = 45.0,
) -> LLMRouter:
    ordered = [providers[name] for name in chain if name in providers]
    return LLMRouter(
        ordered,
        breaker,
        chaos=set(chaos.get("disabled_providers", [])),
        call_timeout_s=call_timeout_s,
        budget_s=budget_s,
    )
