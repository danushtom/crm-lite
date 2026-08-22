"""The worker runs outside the API package and keeps its own copy of the scoring model.

That copy has drifted before. This test pins the two implementations together so any future
change to one fails loudly until the other is updated.
"""

from __future__ import annotations

import importlib.util
import sys
from itertools import product
from pathlib import Path

import pytest

WORKER_SCORING = Path(__file__).resolve().parents[2] / "worker" / "scoring.py"


def _load_worker_scoring():
    spec = importlib.util.spec_from_file_location("worker_scoring", WORKER_SCORING)
    if spec is None or spec.loader is None:
        pytest.skip("worker scoring module not found")
    module = importlib.util.module_from_spec(spec)
    sys.modules["worker_scoring"] = module
    spec.loader.exec_module(module)
    return module


@pytest.mark.skipif(not WORKER_SCORING.exists(), reason="worker app not present")
def test_api_and_worker_scoring_agree():
    from app.domain import scoring as api_scoring

    worker_scoring = _load_worker_scoring()

    values = [None, 0, 150_000, 5_00_000, 15_00_000, 40_00_000]
    currencies = ["INR", "USD"]
    probabilities = [0, 50, 100]
    stages = ["prospect", "negotiation", "won"]
    followups = [None, "2030-01-01"]
    intel = [
        None,
        {"decision_makers": "CTO"},
        {"decision_makers": "a fairly long list of stakeholder names here"},
        {"strategic_notes": "spoke to the founder"},
    ]

    for value, currency, probability, stage, followup, intelligence in product(
        values, currencies, probabilities, stages, followups, intel
    ):
        kwargs = dict(
            estimated_value=value,
            currency=currency,
            deal_probability=probability,
            stage=stage,
            next_followup_date=followup,
            intelligence=intelligence,
            score_override=None,
        )
        assert api_scoring.compute_priority_score(**kwargs) == worker_scoring.compute_priority_score(
            **kwargs
        ), f"scoring drift for {kwargs}"
