from fastapi.testclient import TestClient

from app import main


def test_research_opportunity_builds_queries_before_charging(monkeypatch):
    monkeypatch.setattr(
        main,
        "get_research_opportunity",
        lambda api_key, run_id: {
            "product_directions": [
                {"pain": "pain-a"},
                {"pain": "pain-b"},
                {"pain": "pain-a"},
                {"pain": "pain-c"},
            ]
        },
    )
    charges = []
    monkeypatch.setattr(
        main,
        "_charge",
        lambda api_key, endpoint, credits=1: charges.append(credits) or credits,
    )
    monkeypatch.setattr(main, "_usage_headers", lambda request, api_key, credits_used=None: {})

    async def fake_search(query, marketplaces, limit):
        return {
            "results": [
                {
                    "url": f"https://example.com/{query}",
                    "product": {
                        "product": {"title": query},
                        "pricing": {"price": 100, "currency": "JPY"},
                        "source": {"marketplace": marketplaces[0], "product_id": query},
                    },
                }
            ]
        }

    monkeypatch.setattr(main, "search_products", fake_search)
    main.app.dependency_overrides[main.get_api_key] = lambda: "test-key"
    try:
        client = TestClient(main.app)
        response = client.get(
            "/v1/research/runs/run-1/opportunity",
            headers={"X-API-Key": "test-key"},
        )
    finally:
        main.app.dependency_overrides.pop(main.get_api_key, None)

    assert response.status_code == 200
    assert charges == [30]
    assert len(response.json()["product_candidates"]) == 3
    assert response.json()["credits"] == 30
