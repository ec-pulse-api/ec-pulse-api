from app.main import _consumer_insight_credit_cost


def test_consumer_insight_credit_cost_uses_ceiling_per_50_comments():
    assert _consumer_insight_credit_cost(1) == 1
    assert _consumer_insight_credit_cost(50) == 1
    assert _consumer_insight_credit_cost(51) == 2
    assert _consumer_insight_credit_cost(99) == 2
    assert _consumer_insight_credit_cost(100) == 2
    assert _consumer_insight_credit_cost(101) == 3
