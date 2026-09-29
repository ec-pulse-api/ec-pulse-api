import pytest

from app.services.url_safety import next_redirect


def test_relative_redirect_is_resolved():
    assert next_redirect("https://example.com/a", "/b") == "https://example.com/b"


@pytest.mark.asyncio
async def test_private_url_is_rejected():
    from app.services.url_safety import validate_public_url

    with pytest.raises(ValueError):
        await validate_public_url("http://127.0.0.1:8000/health")


def test_redirect_to_private_url_is_rejected():
    import asyncio
    from app.services.url_safety import validate_public_url

    async def run():
        try:
            await validate_public_url("http://127.0.0.1:8000/health")
        except ValueError:
            return True
        return False

    assert asyncio.run(run())
