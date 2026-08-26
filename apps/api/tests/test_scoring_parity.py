"""The API and the worker must run one scoring implementation, not two that agree.

They used to hold separate copies, and those copies had drifted: one guarded
``decision_makers`` against non-string values and the other did not, so the same lead could
score differently depending on which process last touched it. A parity test across hundreds
of inputs pinned them together, but a test asserting two things are identical is a workaround
for their being two things.

Both now install the workspace package ``dracara-scoring``. What is worth testing is that
this stays true -- that neither app has quietly reintroduced a local copy.
"""

from __future__ import annotations

import importlib.util
import sys
from itertools import product
from pathlib import Path

import pytest

WORKER_DIR = Path(__file__).resolve().parents[2] / "worker"
WORKER_SCORING = WORKER_DIR / "scoring.py"


def test_api_scoring_comes_from_the_shared_package():
    from app.domain import scoring as api_scoring

    import dracara_scoring

    assert api_scoring.compute_priority_score is dracara_scoring.compute_priority_score


@pytest.mark.skipif(not WORKER_SCORING.exists(), reason="worker app not present")
def test_worker_scoring_comes_from_the_same_shared_package():
    import dracara_scoring

    spec = importlib.util.spec_from_file_location("worker_scoring_check", WORKER_SCORING)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules["worker_scoring_check"] = module
    spec.loader.exec_module(module)

    assert module.compute_priority_score is dracara_scoring.compute_priority_score, (
        "the worker has its own scoring implementation again; it must re-export "
        "dracara-scoring so both processes score a lead identically"
    )


def test_scoring_is_deterministic_across_the_input_space():
    """Characterisation: the model stays within range and never raises on real-world input."""
    from dracara_scoring import compute_priority_score

    values = [None, 0, 150_000, 5_00_000, 15_00_000, 40_00_000]
    currencies = ["INR", "USD"]
    probabilities = [0, 50, 100]
    stages = ["prospect", "negotiation", "won"]
    followups = [None, "2030-01-01"]
    intel = [
        None,
        {"decision_makers": "CTO"},
        {"decision_makers": 12345},
        {"decision_makers": "a fairly long list of stakeholder names here"},
        {"strategic_notes": "spoke to the founder"},
    ]

    for value, currency, probability, stage, followup, intelligence in product(
        values, currencies, probabilities, stages, followups, intel
    ):
        score = compute_priority_score(
            estimated_value=value,
            currency=currency,
            deal_probability=probability,
            stage=stage,
            next_followup_date=followup,
            intelligence=intelligence,
            score_override=None,
        )
        assert 0 <= score <= 100
        assert isinstance(score, int)
