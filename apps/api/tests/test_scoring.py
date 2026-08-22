from app.domain.scoring import compute_priority_score


def test_score_respects_override():
    assert (
        compute_priority_score(
            estimated_value=None,
            currency="INR",
            deal_probability=50,
            stage="prospect",
            next_followup_date=None,
            intelligence=None,
            score_override=88,
        )
        == 88
    )


def test_score_range_without_override():
    score = compute_priority_score(
        estimated_value=15_00_000,
        currency="INR",
        deal_probability=60,
        stage="proposal_sent",
        next_followup_date="2030-01-01",
        intelligence={"decision_makers": "CTO and Founder"},
        score_override=None,
    )
    assert 0 <= score <= 100


def test_override_is_clamped_to_valid_range():
    kwargs = dict(
        estimated_value=None,
        currency="INR",
        deal_probability=50,
        stage="prospect",
        next_followup_date=None,
        intelligence=None,
    )
    assert compute_priority_score(score_override=250, **kwargs) == 100
    assert compute_priority_score(score_override=-10, **kwargs) == 0


def test_seniority_in_decision_makers_raises_score():
    base = dict(
        estimated_value=5_00_000,
        currency="INR",
        deal_probability=50,
        stage="contacting",
        next_followup_date=None,
        score_override=None,
    )
    junior = compute_priority_score(intelligence={"decision_makers": "intern"}, **base)
    senior = compute_priority_score(intelligence={"decision_makers": "CTO"}, **base)
    assert senior > junior


def test_non_string_decision_makers_does_not_crash():
    """decision_makers arrives from JSON and is not guaranteed to be a string."""
    score = compute_priority_score(
        estimated_value=100000,
        currency="INR",
        deal_probability=50,
        stage="prospect",
        next_followup_date=None,
        intelligence={"decision_makers": 12345},
        score_override=None,
    )
    assert 0 <= score <= 100
