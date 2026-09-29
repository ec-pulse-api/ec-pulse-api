from app.main import _consumer_insight_credit_cost


def test_consumer_insight_credit_cost_uses_ceiling_per_50_comments():
    assert _consumer_insight_credit_cost(1) == 1
    assert _consumer_insight_credit_cost(50) == 1
    assert _consumer_insight_credit_cost(51) == 2
    assert _consumer_insight_credit_cost(99) == 2
    assert _consumer_insight_credit_cost(100) == 2
    assert _consumer_insight_credit_cost(101) == 3



def test_research_opportunity_credit_cost_mirrors_product_search_unit():
    from app.main import _research_opportunity_credit_cost

    assert _research_opportunity_credit_cost(0) == 1
    assert _research_opportunity_credit_cost(1) == 15
    assert _research_opportunity_credit_cost(2) == 30
    assert _research_opportunity_credit_cost(3) == 45
