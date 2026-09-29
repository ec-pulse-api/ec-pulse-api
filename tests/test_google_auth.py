from fastapi.testclient import TestClient
from app.main import app


def test_google_login_requires_configuration(monkeypatch):
    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_PUBLISHABLE_KEY", raising=False)
    response = TestClient(app).get("/auth/google", follow_redirects=False)
    assert response.status_code == 503


def test_google_login_redirect(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    monkeypatch.setenv("APP_BASE_URL", "https://ec-pulse-api.vercel.app")
    response = TestClient(app).get("/auth/google", follow_redirects=False)
    assert response.status_code == 302
    assert response.headers["location"].startswith("https://example.supabase.co/auth/v1/authorize?")
    assert "provider=google" in response.headers["location"]
    assert "ecp_oauth_verifier=" in response.headers["set-cookie"]


def test_current_user_requires_session(monkeypatch):
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_PUBLISHABLE_KEY", "sb_publishable_test")
    response = TestClient(app).get("/auth/me")
    assert response.status_code == 401
