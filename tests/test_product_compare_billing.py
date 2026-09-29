from fastapi.testclient import TestClient

from app import main


def test_product_compare_returns_charged_credits(monkeypatch):
    monkeypatch.setattr(main, "_validate_urls", lambda urls: None)
    monkeypatch.setattr(main, "_charge", lambda api_key, endpoint, credits=1: {"credits_used": credits, "credits_remaining": 90})
    monkeypatch.setattr(main, "_usage_headers", lambda request, api_key, result=None: {})

    async def fake_fetch(url):
        return (
            {
                "source": {"url": url, "marketplace": "test", "product_id": url},
                "product": {"title": "Test"},
                "pricing": {"price": 100, "currency": "JPY"},
            },
            False,
        )

    monkeypatch.setattr(main, "fetch_product_cached", fake_fetch)
    monkeypatch.setattr(main, "get_api_key", lambda: "test-key")

    client = TestClient(main.app)
    response = client.post(
        "/v1/products/compare",
        json={"urls": ["https://example.com/a", "https://example.com/b"]},
        headers={"X-API-Key": "test-key"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["credits"]["credits_used"] == 2
    assert body["successful"] == 2
