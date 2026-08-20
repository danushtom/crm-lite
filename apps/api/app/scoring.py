"""Weighted opportunity score (tdd.md §12.2)."""

from __future__ import annotations

from typing import Any


def clamp01(x: float) -> float:
    return max(0.0, min(100.0, x))


def dimension_budget_fit(estimated_value: float | None, currency: str = "INR") -> float:
    """Normalize estimated deal size vs typical agency band."""
    if estimated_value is None or estimated_value <= 0:
        return 40.0
    # Rough INR bands — adjustable later via settings
    if currency != "INR":
        estimated_value = estimated_value * 83.0  # naive USD→INR for scoring only
    if estimated_value >= 30_00_000:
        return 95.0
    if estimated_value >= 10_00_000:
        return 80.0
    if estimated_value >= 5_00_000:
        return 65.0
    if estimated_value >= 2_00_000:
        return 55.0
    return 45.0


def dimension_urgency(next_followup_date: str | None, _stage: str) -> float:
    if not next_followup_date:
        return 50.0
    # Hotter if follow-up soon — simplified
    return 70.0


def dimension_authority(intelligence: dict[str, Any] | None) -> float:
    if not intelligence:
        return 50.0
    dm = intelligence.get("decision_makers") or ""
    sn = intelligence.get("strategic_notes") or ""
    text = f"{dm}\n{sn}".lower()
    if any(k in text for k in ("cto", "founder", "ceo", "vp", "director")):
        return 85.0
    if len(dm.strip()) > 20:
        return 75.0
    return 55.0


def dimension_project_size(estimated_value: float | None, currency: str = "INR") -> float:
    return dimension_budget_fit(estimated_value, currency) * 0.85


def dimension_probability(deal_probability: int) -> float:
    return float(deal_probability)


def compute_priority_score(
    *,
    estimated_value: float | None,
    currency: str,
    deal_probability: int,
    stage: str,
    next_followup_date: str | None,
    intelligence: dict[str, Any] | None,
    score_override: int | None,
) -> int:
    if score_override is not None:
        return max(0, min(100, score_override))
    budget_fit = dimension_budget_fit(estimated_value, currency)
    urgency = dimension_urgency(next_followup_date, stage)
    authority = dimension_authority(intelligence)
    proj_size = dimension_project_size(estimated_value, currency)
    probability = dimension_probability(deal_probability)

    raw = (
        budget_fit * 0.25
        + urgency * 0.20
        + authority * 0.20
        + proj_size * 0.15
        + probability * 0.20
    )
    return int(round(clamp01(raw)))
