import pytest

from app.services.url_safety import next_redirect


def test_relative_redirect_is_resolved():
    assert next_redirect("https://example.com/a", "/b") == "https://example.com/b"


@pytest.mark.asyncio
async def test_private_url_is_rejected():
    from app.services.url_safety import validate_public_url

    with pytest.raises(ValueError):
        await validate_public_url("http://127.0.0.1:8000/health")


@pytest.mark.asyncio
async def test_nonstandard_port_is_rejected():
    from app.services.url_safety import validate_public_url

    with pytest.raises(ValueError):
        await validate_public_url("https://example.com:8080/")


@pytest.mark.asyncio
async def test_url_credentials_are_rejected():
    from app.services.url_safety import validate_public_url

    with pytest.raises(ValueError):
        await validate_public_url("https://user:pass@example.com/")


@pytest.mark.asyncio
async def test_oversized_url_is_rejected():
    from app.services.url_safety import validate_public_url

    with pytest.raises(ValueError):
        await validate_public_url("https://example.com/" + "a" * 2048)

@pytest.mark.asyncio
async def test_shared_address_space_is_rejected(monkeypatch):
    from app.services import url_safety

    def fake_getaddrinfo(*args, **kwargs):
        return [(None, None, None, None, ("100.64.0.1", 0))]

    monkeypatch.setattr(url_safety.socket, "getaddrinfo", fake_getaddrinfo)
    with pytest.raises(ValueError):
        await url_safety.validate_public_url("https://example.com/")
