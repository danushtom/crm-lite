"""Token accounting.

Every LLM call in a multi-tenant product is billable to *some* organization, and this product
shares one API key across all of them. A call whose tokens are not attributed is a cost nobody can
explain later, so each graph returns a :class:`UsageRecord` alongside its result and the caller
persists it to ``public.ai_usage``.

Costs here are a convenience, not an invoice: the authoritative figures are the token counts. The
table below is a snapshot of published per-million-token pricing and will go stale -- update it
when it does, or set every value to zero and read cost out of the provider's own billing.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

#: USD per 1M tokens, as (input, output). Approximate; see the module docstring.
_PRICE_PER_MILLION: dict[str, tuple[float, float]] = {
    "gpt-4o": (2.50, 10.00),
    "gpt-4o-mini": (0.15, 0.60),
    "text-embedding-3-small": (0.02, 0.0),
    "text-embedding-3-large": (0.13, 0.0),
}


def estimate_cost_usd(model: str, prompt_tokens: int, completion_tokens: int) -> float:
    """Best-effort cost. Unknown models cost 0.0 rather than raising -- a new model id should
    not break a feature, it should just show up as un-priced until the table is updated."""
    prices = _PRICE_PER_MILLION.get(model)
    if prices is None:
        # Try the base name, so "gpt-4o-2024-11-20" still prices as "gpt-4o".
        for known, known_prices in _PRICE_PER_MILLION.items():
            if model.startswith(known):
                prices = known_prices
                break
    if prices is None:
        return 0.0
    input_price, output_price = prices
    return (prompt_tokens * input_price + completion_tokens * output_price) / 1_000_000


@dataclass(slots=True)
class UsageRecord:
    """What one AI feature consumed. Maps one-to-one onto a ``public.ai_usage`` row."""

    feature: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    #: Spend that is not token-priced -- web search is billed per request, in dollars.
    extra_cost_usd: float = 0.0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    @property
    def cost_usd(self) -> float:
        return (
            estimate_cost_usd(self.model, self.prompt_tokens, self.completion_tokens)
            + self.extra_cost_usd
        )

    def add(self, usage: Any) -> "UsageRecord":
        """Accumulate one provider usage object. A graph makes several model calls; they bill as
        one record so a feature's cost is a single row, not one row per node."""
        if usage is not None:
            self.prompt_tokens += int(getattr(usage, "prompt_tokens", 0) or 0)
            self.completion_tokens += int(getattr(usage, "completion_tokens", 0) or 0)
        return self

    def to_row(self, organization_id: str) -> dict[str, Any]:
        """The ``ai_usage`` insert payload. ``organization_id`` is supplied by the caller, which
        is the only place that knows it -- this package never resolves a tenant."""
        return {
            "organization_id": organization_id,
            "feature": self.feature,
            "model": self.model,
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "cost_usd": round(self.cost_usd, 6),
            "metadata": self.metadata,
        }
