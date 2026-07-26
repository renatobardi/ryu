"""Tabela de preços por provider:model + estimativa de custo.

Port funcional de server/internal/metrics/pricing.go do multica:
- ModelPrice: input/output/cache_read/cache_write por MILHÃO de tokens.
- price_for_model_alias(model): resolve ids "sujos" (prefixos provider/,
  datas, variantes com ponto/hífen) para a linha de preço canônica.
- estimate_cost_usd(...): estimativa quando o provider NÃO reportou custo
  autoritativo (linha "uncosted" — split costed/uncosted da migração 213).

Regra de ouro (paridade multica): custo reportado pelo provider é
AUTORITATIVO e nunca é recalculado; a estimativa só cobre o restante.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class ModelPrice:
    provider: str
    model: str
    input_per_m: float
    cache_read_per_m: float
    cache_write_per_m: float
    output_per_m: float


# provider:model -> preço (US$ por 1M tokens) — espelho de pricing.go
MODEL_PRICES: dict[str, ModelPrice] = {
    k: ModelPrice(k.split(":")[0], k.split(":", 1)[1], *v)
    for k, v in {
        # (input, cache_read, cache_write, output)
        "openai:gpt-5.6-sol": (5.00, 0.50, 6.25, 30.00),
        "openai:gpt-5.6-terra": (2.50, 0.25, 3.125, 15.00),
        "openai:gpt-5.6-luna": (1.00, 0.10, 1.25, 6.00),
        "openai:gpt-5.5": (5.00, 0.50, 0.50, 30.00),
        "openai:gpt-5.4": (2.50, 0.25, 0.25, 15.00),
        "openai:gpt-5.4-mini": (0.75, 0.075, 0.075, 4.50),
        "openai:gpt-5.3-codex": (1.75, 0.175, 0.175, 14.00),
        "openai:gpt-5.2-codex": (1.75, 0.175, 0.175, 14.00),
        "anthropic:claude-sonnet-5": (2.00, 0.20, 2.50, 10.00),
        "anthropic:claude-fable-5": (10.00, 1.00, 12.50, 50.00),
        "anthropic:claude-opus-5": (5.00, 0.50, 6.25, 25.00),
        "anthropic:claude-opus-4.8": (5.00, 0.50, 6.25, 25.00),
        "anthropic:claude-opus-4.7": (5.00, 0.50, 6.25, 25.00),
        "anthropic:claude-opus-4.6": (5.00, 0.50, 6.25, 25.00),
        "anthropic:claude-opus-4.5": (5.00, 0.50, 6.25, 25.00),
        "anthropic:claude-sonnet-4.6": (3.00, 0.30, 3.75, 15.00),
        "anthropic:claude-sonnet-4.5": (3.00, 0.30, 3.75, 15.00),
        "anthropic:claude-haiku-4.5": (1.00, 0.10, 1.25, 5.00),
        "deepseek:v4-pro": (1.74, 0.0145, 1.74, 3.48),
        "deepseek:v4-flash": (0.56, 0.0112, 0.56, 1.12),
        "minimax:m2.7": (0.30, 0.06, 0.375, 1.20),
        "minimax:m2.7-highspeed": (0.60, 0.06, 0.375, 2.40),
        "google:gemini-3-flash": (0.50, 0.05, 0.50, 3.00),
        "google:gemini-3.1-pro": (2.00, 0.20, 2.00, 12.00),
        "google:gemini-2.5-pro": (1.25, 0.31, 1.25, 10.00),
        "google:gemini-2.5-flash": (0.30, 0.03, 0.30, 2.50),
        "xai:grok-4.5": (2.00, 0.30, 2.00, 6.00),
        "xai:grok-4.3": (1.25, 0.20, 1.25, 2.50),
        "xai:grok-build-0.1": (1.00, 0.20, 1.00, 2.00),
        "xai:grok-4.20-multi-agent-0309": (1.25, 0.20, 1.25, 2.50),
        "xai:grok-4.20-0309-reasoning": (1.25, 0.20, 1.25, 2.50),
        "xai:grok-4.20-0309-non-reasoning": (1.25, 0.20, 1.25, 2.50),
    }.items()
}

# regras de alias (espelho de modelAliasRules do pricing.go)
_ALIAS_RULES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"(^|/|:)gpt-5\.6-sol$"), "openai:gpt-5.6-sol"),
    (re.compile(r"(^|/|:)gpt-5\.6-terra$"), "openai:gpt-5.6-terra"),
    (re.compile(r"(^|/|:)gpt-5\.6-luna$"), "openai:gpt-5.6-luna"),
    (re.compile(r"(^|/|:)gpt-5[.-]5$|^gpt-5-5$"), "openai:gpt-5.5"),
    (re.compile(r"(^|/|:)gpt-5[.-]4($|-2026-03-05|-xhigh)"), "openai:gpt-5.4"),
    (re.compile(r"(^|/|:)gpt-5[.-]4-mini($|[^a-z0-9])"), "openai:gpt-5.4-mini"),
    (re.compile(r"(^|/|:)gpt-5[.-]3-codex$"), "openai:gpt-5.3-codex"),
    (re.compile(r"(^|/|:)gpt-5[.-]2-codex$"), "openai:gpt-5.2-codex"),
    (re.compile(r"claude-sonnet-5|claude-5-sonnet"), "anthropic:claude-sonnet-5"),
    (re.compile(r"claude-fable-5"), "anthropic:claude-fable-5"),
    (re.compile(r"claude-opus-5"), "anthropic:claude-opus-5"),
    (re.compile(r"claude-opus-4[-.]8"), "anthropic:claude-opus-4.8"),
    (re.compile(r"claude-opus-4[-.]7"), "anthropic:claude-opus-4.7"),
    (re.compile(r"claude-opus-4[-.]6"), "anthropic:claude-opus-4.6"),
    (re.compile(r"claude-opus-4[-.]5"), "anthropic:claude-opus-4.5"),
    (re.compile(r"claude-sonnet-4[-.]6|claude-4[-.]6-sonnet"), "anthropic:claude-sonnet-4.6"),
    (re.compile(r"claude-sonnet-4[-.]5|claude-4[-.]5-sonnet"), "anthropic:claude-sonnet-4.5"),
    (re.compile(r"claude-haiku-4[-.]5"), "anthropic:claude-haiku-4.5"),
    (re.compile(r"deepseek-v4-pro"), "deepseek:v4-pro"),
    (re.compile(r"deepseek-v4-flash|^deepseek-chat$|^deepseek-reasoner$"), "deepseek:v4-flash"),
    (re.compile(r"minimax-m2[.]7.*highspeed|highspeed.*minimax-m2[.]7"), "minimax:m2.7-highspeed"),
    (re.compile(r"minimax-m2[.]7"), "minimax:m2.7"),
    (re.compile(r"gemini-3-flash"), "google:gemini-3-flash"),
    (re.compile(r"gemini-3[.]1-pro"), "google:gemini-3.1-pro"),
    (re.compile(r"gemini-2[.]5-pro"), "google:gemini-2.5-pro"),
    (re.compile(r"gemini-2[.]5-flash"), "google:gemini-2.5-flash"),
    (re.compile(r"(^|/|:)grok-4\.5$"), "xai:grok-4.5"),
    (re.compile(r"(^|/|:)grok-4\.3$"), "xai:grok-4.3"),
    (re.compile(r"(^|/|:)grok-build-0\.1$"), "xai:grok-build-0.1"),
    (re.compile(r"(^|/|:)grok-4\.20-multi-agent-0309$"), "xai:grok-4.20-multi-agent-0309"),
    (re.compile(r"(^|/|:)grok-4\.20-0309-reasoning$"), "xai:grok-4.20-0309-reasoning"),
    (re.compile(r"(^|/|:)grok-4\.20-0309-non-reasoning$"), "xai:grok-4.20-0309-non-reasoning"),
]


def price_for_model_alias(model: str) -> ModelPrice | None:
    """PriceForModelAlias: id de modelo (com ou sem provider) → preço, ou None."""
    m = (model or "").strip().lower()
    if not m:
        return None
    key = f"{m}"
    if key in MODEL_PRICES:
        return MODEL_PRICES[key]
    for rule, price_key in _ALIAS_RULES:
        if rule.search(m):
            return MODEL_PRICES.get(price_key)
    return None


def _token_cost(tokens: int, per_m: float) -> float:
    if not tokens or tokens <= 0 or per_m <= 0:
        return 0.0
    return tokens * per_m / 1_000_000


def estimate_cost_usd(
    provider: str,
    model: str,
    input_tokens: int = 0,
    output_tokens: int = 0,
    cache_read_tokens: int = 0,
    cache_write_tokens: int = 0,
) -> float | None:
    """Estimativa a partir da tabela; None quando o modelo não está mapeado
    (fica 'unpriced' — nunca chuta preço de modelo desconhecido)."""
    price = price_for_model_alias(model) or price_for_model_alias(f"{provider}:{model}")
    if price is None:
        return None
    return round(
        _token_cost(input_tokens, price.input_per_m)
        + _token_cost(output_tokens, price.output_per_m)
        + _token_cost(cache_read_tokens, price.cache_read_per_m)
        + _token_cost(cache_write_tokens, price.cache_write_per_m),
        6,
    )


def effective_cost_usd(row) -> tuple[float, bool]:
    """(custo efetivo, costed) de uma linha TaskUsage.

    - costed=True: provider reportou custo autoritativo (usa row.cost_usd).
    - costed=False: estima pela tabela (0.0 quando modelo não mapeado).
    """
    if getattr(row, "costed", False):
        return float(row.cost_usd or 0.0), True
    est = estimate_cost_usd(
        row.provider or "",
        row.model or "",
        row.input_tokens or 0,
        row.output_tokens or 0,
        row.cache_read_tokens or 0,
        row.cache_write_tokens or 0,
    )
    return (est if est is not None else 0.0), False
