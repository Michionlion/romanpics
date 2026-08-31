from __future__ import annotations

import httpx
import pytest

from romanpics_api.services.linkcheck import _check_one
from romanpics_api.services.security import (
    daily_network_hmac,
    read_visitor,
    sign_visitor,
    url_host_allowed,
)


def test_signed_visitor_rejects_tampering_and_network_token_has_no_ip():
    secret = "test-secret-long-enough-for-hmac"
    actor = "4c263736-41ed-5918-abac-8edf0bd38db8"
    signed = sign_visitor(actor, secret)
    assert read_visitor(signed, secret) == actor
    assert read_visitor(signed[:-1] + ("a" if signed[-1] != "a" else "b"), secret) is None
    token = daily_network_hmac("203.0.113.42", secret)
    assert token and "203.0.113" not in token


def test_allowlist_rejects_ports_credentials_and_private_literals():
    allowed = ("nasa.gov", "127.0.0.1")
    assert url_host_allowed("https://images.nasa.gov/x", allowed)
    assert not url_host_allowed("http://images.nasa.gov/x", allowed)
    assert not url_host_allowed("https://images.nasa.gov:8443/x", allowed)
    assert not url_host_allowed("https://user@images.nasa.gov/x", allowed)
    assert not url_host_allowed("https://127.0.0.1/x", allowed)
    assert not url_host_allowed("https://images.nasa.gov.evil.test/x", allowed)


@pytest.mark.asyncio
async def test_linkcheck_validates_redirect_before_following_it():
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://evil.test/original.fits"})

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(handler), follow_redirects=True
    ) as client:
        result = await _check_one(
            client,
            "https://images.nasa.gov/start",
            ("images.nasa.gov",),
            resolve_dns=False,
        )
    assert result[0] is False
    assert "allowlist" in result[3]
    assert requests == ["https://images.nasa.gov/start"]


@pytest.mark.asyncio
async def test_linkcheck_rejects_private_redirect_even_if_literal_is_listed():
    requests: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(str(request.url))
        return httpx.Response(302, headers={"Location": "https://127.0.0.1/secret"})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await _check_one(
            client,
            "https://images.nasa.gov/start",
            ("images.nasa.gov", "127.0.0.1"),
            resolve_dns=False,
        )
    assert result[0] is False
    assert requests == ["https://images.nasa.gov/start"]


@pytest.mark.asyncio
async def test_linkcheck_range_fallback_does_not_read_response_body():
    methods: list[str] = []

    class ExplodingStream(httpx.AsyncByteStream):
        async def __aiter__(self):
            raise AssertionError("link checker attempted to consume an original")
            yield b""  # pragma: no cover

    def handler(request: httpx.Request) -> httpx.Response:
        methods.append(request.method)
        if request.method == "HEAD":
            return httpx.Response(405)
        assert request.headers["range"] == "bytes=0-0"
        return httpx.Response(200, stream=ExplodingStream())

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        result = await _check_one(
            client,
            "https://images.nasa.gov/original.fits",
            ("images.nasa.gov",),
            resolve_dns=False,
        )
    assert result[0] is True
    assert methods == ["HEAD", "GET"]
