# dracara-scoring

The weighted opportunity score (`tdd.md` §12.2), as one implementation.

It previously existed twice — `apps/api/app/domain/scoring.py` and
`apps/worker/scoring.py` — because the worker runs outside the API's package path. The two
copies drifted: one guarded `decision_makers` against non-string values and the other did
not, so the same lead could score differently depending on which process last touched it.
A parity test across 864 input combinations pinned them together, but a test that asserts
two things are identical is a workaround for their being two things.

Both apps now install this package from the workspace:

```
-e ../../packages/scoring
```

## Usage

```python
from dracara_scoring import compute_priority_score

score = compute_priority_score(
    estimated_value=1_500_000,
    currency="INR",
    deal_probability=60,
    stage="proposal_sent",
    next_followup_date="2026-09-01",
    intelligence={"decision_makers": "CTO"},
    score_override=None,
)
```
