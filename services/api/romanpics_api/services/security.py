from __future__ import annotations

import base64
import hashlib
import hmac
import ipaddress
import secrets
import uuid
from datetime import UTC, datetime
from urllib.parse import urlsplit


def sign_visitor(actor_id: str, secret: str) -> str:
    uuid.UUID(actor_id)
    payload = f"v1.{actor_id}"
    signature = hmac.new(secret.encode(), payload.encode(), hashlib.sha256).digest()
    encoded = base64.urlsafe_b64encode(signature).rstrip(b"=").decode()
    return f"{payload}.{encoded}"


def read_visitor(value: str | None, secret: str) -> str | None:
    if not value:
        return None
    try:
        version, actor_id, signature = value.split(".", 2)
        if version != "v1":
            return None
        uuid.UUID(actor_id)
    except (ValueError, AttributeError):
        return None
    expected = sign_visitor(actor_id, secret).rsplit(".", 1)[1]
    return actor_id if secrets.compare_digest(signature, expected) else None


def new_actor() -> str:
    return str(uuid.uuid4())


def daily_network_hmac(address: str | None, secret: str, now: datetime | None = None) -> str | None:
    if not address:
        return None
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return None
    if isinstance(ip, ipaddress.IPv4Address):
        network = ipaddress.ip_network(f"{ip}/24", strict=False)
    else:
        network = ipaddress.ip_network(f"{ip}/56", strict=False)
    day = (now or datetime.now(UTC)).date().isoformat()
    payload = f"{day}:{network.network_address}/{network.prefixlen}"
    return hmac.new(secret.encode(), payload.encode(), hashlib.sha256).hexdigest()


def url_host_allowed(url: str, allowed_hosts: tuple[str, ...]) -> bool:
    try:
        parsed = urlsplit(url)
    except ValueError:
        return False
    try:
        port = parsed.port
    except ValueError:
        return False
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or port not in (None, 443)
    ):
        return False
    hostname = parsed.hostname.lower().rstrip(".")
    try:
        literal_ip = ipaddress.ip_address(hostname)
    except ValueError:
        literal_ip = None
    if literal_ip is not None and not literal_ip.is_global:
        return False
    return any(hostname == host or hostname.endswith(f".{host}") for host in allowed_hosts)


def encode_cursor(offset: int) -> str:
    payload = f"offset:{max(0, offset)}".encode()
    return base64.urlsafe_b64encode(payload).rstrip(b"=").decode()


def decode_cursor(cursor: str | None) -> int:
    if not cursor:
        return 0
    try:
        padding = "=" * (-len(cursor) % 4)
        payload = base64.urlsafe_b64decode(cursor + padding).decode()
        prefix, offset = payload.split(":", 1)
        value = int(offset)
    except (ValueError, UnicodeDecodeError):
        raise ValueError("invalid cursor") from None
    if prefix != "offset" or value < 0:
        raise ValueError("invalid cursor")
    return value
