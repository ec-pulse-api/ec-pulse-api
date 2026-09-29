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


@pytest.mark.asyncio
async def test_safe_transport_connects_to_current_public_resolution(monkeypatch):
    from app.services import url_safety

    transport = url_safety.safe_async_transport()
    backend = transport._pool._network_backend
    captured = {}

    def fake_getaddrinfo(*args, **kwargs):
        return [(None, None, None, None, ("93.184.216.34", 0))]

    async def fake_connect_tcp(host, port, **kwargs):
        captured["host"] = host
        captured["port"] = port
        return object()

    monkeypatch.setattr(url_safety.socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(backend._backend, "connect_tcp", fake_connect_tcp)

    await backend.connect_tcp("example.com", 443)
    assert captured == {"host": "93.184.216.34", "port": 443}


@pytest.mark.asyncio
async def test_safe_transport_rejects_dns_rebinding_to_private_ip(monkeypatch):
    from app.services import url_safety

    transport = url_safety.safe_async_transport()
    backend = transport._pool._network_backend

    def fake_getaddrinfo(*args, **kwargs):
        return [(None, None, None, None, ("127.0.0.1", 0))]

    async def fail_connect_tcp(*args, **kwargs):
        raise AssertionError("TCP connection must not be attempted")

    monkeypatch.setattr(url_safety.socket, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setattr(backend._backend, "connect_tcp", fail_connect_tcp)

    with pytest.raises(ValueError, match="Private or local network"):
        await backend.connect_tcp("example.com", 443)
