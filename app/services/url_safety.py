import asyncio
import ipaddress
import socket
from urllib.parse import urljoin, urlparse

MAX_REDIRECTS = 5
_ALLOWED_PORTS = {80, 443}


def _blocked_ip(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


async def validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("A valid public http(s) URL is required")
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("URL credentials are not allowed")
    if parsed.port not in (None, *_ALLOWED_PORTS):
        raise ValueError("Only ports 80 and 443 are allowed")

    host = parsed.hostname
    try:
        addresses = await asyncio.to_thread(
            socket.getaddrinfo,
            host,
            parsed.port or (443 if parsed.scheme == "https" else 80),
            type=socket.SOCK_STREAM,
        )
    except OSError as exc:
        raise ValueError("Unable to resolve the URL host") from exc

    resolved = {item[4][0] for item in addresses if item[4]}
    if not resolved or any(_blocked_ip(address) for address in resolved):
        raise ValueError("Private or local network URLs are not allowed")

    return url


def next_redirect(base_url: str, location: str) -> str:
    return urljoin(base_url, location)
