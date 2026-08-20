from app.scoring import compute_priority_score


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
    s = compute_priority_score(
        estimated_value=15_00_000,
        currency="INR",
        deal_probability=60,
        stage="proposal_sent",
        next_followup_date="2030-01-01",
        intelligence={"decision_makers": "CTO and Founder"},
        score_override=None,
    )
    assert 0 <= s <= 100
