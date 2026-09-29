from types import SimpleNamespace

import app.main as main


def test_usage_headers_accept_integer_credit_charge(monkeypatch):
    monkeypatch.setattr(
        main,
        "ensure_api_account",
        lambda api_key: {"plan": "free", "credits_balance": 97},
    )
    monkeypatch.setattr(
        main,
        "check_rate_limit",
        lambda key_hash, plan: {
            "limit": 30,
            "remaining": 29,
            "reset_seconds": 12,
        },
    )
    request = SimpleNamespace(state=SimpleNamespace(rate_limit={
        "limit": 30,
        "remaining": 29,
        "reset_seconds": 12,
    }))

    headers = main._usage_headers(request, "test-key", 3)

    assert headers["X-EC-Credits-Used"] == "3"
    assert headers["X-EC-Credits-Remaining"] == "97"
    assert headers["X-RateLimit-Limit"] == "30"


def test_usage_headers_preserves_zero_credit_value(monkeypatch):
    monkeypatch.setattr(
        main,
        "ensure_api_account",
        lambda api_key: {"plan": "free", "credits_balance": 100},
    )
    monkeypatch.setattr(
        main,
        "check_rate_limit",
        lambda key_hash, plan: {
            "limit": 30,
            "remaining": 30,
            "reset_seconds": 60,
        },
    )
    request = SimpleNamespace(state=SimpleNamespace(rate_limit={
        "limit": 30,
        "remaining": 30,
        "reset_seconds": 60,
    }))

    headers = main._usage_headers(request, "test-key", 0)

    assert headers["X-EC-Credits-Used"] == "0"
