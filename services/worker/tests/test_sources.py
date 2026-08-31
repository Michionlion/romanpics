from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from pathlib import Path

import pytest

from romanpics_worker.sources import (
    NetworkDisabledError,
    SafeRemoteFetcher,
    SourcePolicy,
    SourceValidationError,
)


class FakeResponse:
    def __init__(self, status: int, headers: Mapping[str, str], chunks: Iterable[bytes] = ()):
        self.status_code = status
        self.headers = dict(headers)
        self.chunks = list(chunks)
        self.closed = False

    def iter_bytes(self, chunk_size: int = 65_536) -> Iterator[bytes]:
        yield from self.chunks

    def close(self) -> None:
        self.closed = True


class FakeTransport:
    def __init__(self, routes: Mapping[str, list[FakeResponse]]):
        self.routes = {url: list(responses) for url, responses in routes.items()}
        self.requests: list[str] = []
        self.closed = False

    def get(self, url: str) -> FakeResponse:
        self.requests.append(url)
        return self.routes[url].pop(0)

    def close(self) -> None:
        self.closed = True


class ProbeTransport:
    def __init__(self, responses: list[FakeResponse]):
        self.responses = responses
        self.requests: list[tuple[str, str, Mapping[str, str] | None]] = []

    def request(
        self, method: str, url: str, *, headers: Mapping[str, str] | None = None
    ) -> FakeResponse:
        self.requests.append((method, url, headers))
        return self.responses.pop(0)

    def get(self, url: str) -> FakeResponse:
        return self.request("GET", url)

    def close(self) -> None:
        pass


def PUBLIC(_host: str) -> list[str]:
    return ["93.184.216.34"]


def policy(**changes: object) -> SourcePolicy:
    values = {"allowed_hosts": frozenset({"archive.example.org"})}
    values.update(changes)
    return SourcePolicy(**values)


def test_network_is_disabled_by_default() -> None:
    transport = FakeTransport({})
    fetcher = SafeRemoteFetcher(policy(), transport=transport, resolver=PUBLIC)
    with pytest.raises(NetworkDisabledError):
        fetcher.fetch_bytes("https://archive.example.org/file.fits")
    assert transport.requests == []


def test_valid_fetch_checks_mime_size_and_cleans_temporary_file(tmp_path: Path) -> None:
    url = "https://archive.example.org/file.fits"
    response = FakeResponse(
        200, {"content-type": "application/fits", "content-length": "6"}, [b"abc", b"def"]
    )
    transport = FakeTransport({url: [response]})
    fetcher = SafeRemoteFetcher(policy(), enabled=True, transport=transport, resolver=PUBLIC)
    parent = tmp_path / "downloads"
    parent.mkdir()
    with fetcher.temporary_file(url, parent=parent) as (path, metadata):
        assert path.read_bytes() == b"abcdef"
        assert metadata.size == 6
        assert metadata.final_url == url
    assert list(parent.iterdir()) == []
    assert response.closed


def test_standard_asdf_media_type_gets_a_renderable_suffix(tmp_path: Path) -> None:
    url = "https://archive.example.org/product"
    transport = FakeTransport(
        {url: [FakeResponse(200, {"content-type": "application/asdf"}, [b"asdf"])]}
    )
    fetcher = SafeRemoteFetcher(policy(), enabled=True, transport=transport, resolver=PUBLIC)
    with fetcher.temporary_file(url, parent=tmp_path) as (path, metadata):
        assert path.suffix == ".asdf"
        assert metadata.content_type == "application/asdf"


def test_redirect_target_is_revalidated_before_second_request() -> None:
    start = "https://archive.example.org/start"
    first = FakeResponse(302, {"location": "https://evil.example.net/file.fits"})
    transport = FakeTransport({start: [first]})
    fetcher = SafeRemoteFetcher(policy(), enabled=True, transport=transport, resolver=PUBLIC)
    with pytest.raises(SourceValidationError, match="not allowlisted"):
        fetcher.fetch_bytes(start)
    assert transport.requests == [start]
    assert first.closed


def test_dns_private_address_and_rebinding_on_redirect_are_rejected() -> None:
    url = "https://archive.example.org/start"
    transport = FakeTransport({url: [FakeResponse(302, {"location": "/next"})]})
    resolutions = iter([["93.184.216.34"], ["127.0.0.1"]])
    fetcher = SafeRemoteFetcher(
        policy(), enabled=True, transport=transport, resolver=lambda _host: next(resolutions)
    )
    with pytest.raises(SourceValidationError, match="non-public"):
        fetcher.fetch_bytes(url)
    assert transport.requests == [url]

    never_called = FakeTransport({})
    private = SafeRemoteFetcher(
        policy(), enabled=True, transport=never_called, resolver=lambda _host: ["169.254.169.254"]
    )
    with pytest.raises(SourceValidationError, match="non-public"):
        private.fetch_bytes(url)
    assert never_called.requests == []


@pytest.mark.parametrize(
    ("headers", "chunks", "message"),
    [
        ({"content-type": "text/html"}, [b"no"], "MIME"),
        ({"content-type": "application/fits", "content-length": "11"}, [], "byte limit"),
        ({"content-type": "application/fits"}, [b"123456", b"78901"], "while streaming"),
    ],
)
def test_mime_declared_size_and_streamed_size_limits(
    headers: Mapping[str, str], chunks: list[bytes], message: str
) -> None:
    url = "https://archive.example.org/file.fits"
    transport = FakeTransport({url: [FakeResponse(200, headers, chunks)]})
    fetcher = SafeRemoteFetcher(
        policy(max_bytes=10), enabled=True, transport=transport, resolver=PUBLIC
    )
    with pytest.raises(SourceValidationError, match=message):
        fetcher.fetch_bytes(url)


def test_policy_rejects_credentials_ports_ip_literals_and_defaults_to_64_mib() -> None:
    source_policy = policy()
    assert source_policy.max_bytes == 64 * 1024 * 1024
    invalid = [
        "http://archive.example.org/a",
        "https://user:pass@archive.example.org/a",
        "https://archive.example.org:444/a",
        "https://127.0.0.1/a",
    ]
    for url in invalid:
        with pytest.raises(SourceValidationError):
            source_policy.validate_url(url)


def test_probe_uses_head_then_a_one_byte_get_without_consuming_body() -> None:
    url = "https://archive.example.org/catalog"
    transport = ProbeTransport(
        [
            FakeResponse(405, {}),
            FakeResponse(206, {"content-type": "application/octet-stream"}, [b"not-consumed"]),
        ]
    )
    fetcher = SafeRemoteFetcher(policy(), enabled=True, transport=transport, resolver=PUBLIC)
    metadata = fetcher.probe(url)
    assert metadata.status_code == 206
    assert transport.requests == [
        ("HEAD", url, None),
        ("GET", url, {"Range": "bytes=0-0"}),
    ]
