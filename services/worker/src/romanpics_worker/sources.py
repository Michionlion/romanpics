"""SSRF-conscious, opt-in fetching of upstream science products.

No request can be made unless ``enabled=True`` and every URL (including every
redirect target) passes an explicit host and content policy.
"""

from __future__ import annotations

import contextlib
import ipaddress
import socket
import tempfile
from collections.abc import Callable, Iterable, Iterator, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from urllib.parse import urljoin, urlsplit, urlunsplit


class SourceValidationError(ValueError):
    """The remote source did not satisfy the configured trust policy."""


class NetworkDisabledError(RuntimeError):
    """Raised when code attempts a fetch without explicitly enabling networking."""


class ResponseLike(Protocol):
    status_code: int
    headers: Mapping[str, str]

    def iter_bytes(self, chunk_size: int = 65_536) -> Iterator[bytes]: ...

    def close(self) -> None: ...


class Transport(Protocol):
    def get(self, url: str) -> ResponseLike: ...

    def request(
        self, method: str, url: str, *, headers: Mapping[str, str] | None = None
    ) -> ResponseLike: ...

    def close(self) -> None: ...


@dataclass(frozen=True)
class SourcePolicy:
    allowed_hosts: frozenset[str] = field(default_factory=frozenset)
    allowed_mime_types: frozenset[str] = field(
        default_factory=lambda: frozenset(
            {
                "application/fits",
                "application/x-fits",
                "image/fits",
                "application/asdf",
                "application/x-asdf",
                "application/octet-stream",
                "image/jpeg",
                "image/png",
                "image/webp",
            }
        )
    )
    max_bytes: int = 64 * 1024 * 1024
    max_redirects: int = 4
    allow_subdomains: bool = False

    def __post_init__(self) -> None:
        normalized = frozenset(host.rstrip(".").lower() for host in self.allowed_hosts)
        object.__setattr__(self, "allowed_hosts", normalized)
        if self.max_bytes <= 0 or self.max_redirects < 0:
            raise ValueError("source limits must be non-negative and max_bytes must be positive")

    def permits_host(self, host: str) -> bool:
        normalized = host.rstrip(".").lower()
        if normalized in self.allowed_hosts:
            return True
        return self.allow_subdomains and any(
            normalized.endswith(f".{root}") for root in self.allowed_hosts
        )

    def validate_url(self, url: str) -> str:
        parsed = urlsplit(url)
        if parsed.scheme.lower() != "https":
            raise SourceValidationError("only HTTPS source URLs are accepted")
        if parsed.username is not None or parsed.password is not None:
            raise SourceValidationError("source URLs may not contain credentials")
        if not parsed.hostname:
            raise SourceValidationError("source URL has no hostname")
        try:
            host = parsed.hostname.encode("idna").decode("ascii").lower().rstrip(".")
        except UnicodeError as error:
            raise SourceValidationError("source hostname is invalid") from error
        try:
            ipaddress.ip_address(host)
        except ValueError:
            pass
        else:
            raise SourceValidationError("IP-literal source URLs are not accepted")
        if not self.permits_host(host):
            raise SourceValidationError(f"source host {host!r} is not allowlisted")
        try:
            port = parsed.port
        except ValueError as error:
            raise SourceValidationError("source URL has an invalid port") from error
        if port not in (None, 443):
            raise SourceValidationError("source URL uses a non-HTTPS port")
        netloc = host if port is None else f"{host}:443"
        return urlunsplit(("https", netloc, parsed.path or "/", parsed.query, ""))


@dataclass(frozen=True)
class FetchMetadata:
    requested_url: str
    final_url: str
    content_type: str
    size: int
    redirects: tuple[str, ...]


@dataclass(frozen=True)
class ProbeMetadata:
    requested_url: str
    final_url: str
    status_code: int
    redirects: tuple[str, ...]


def system_resolver(host: str) -> Iterable[str]:
    """Resolve all addresses without caching so redirects/retries are rechecked."""

    return sorted(
        {record[4][0] for record in socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)}
    )


class HttpxTransport:
    """The production transport, imported and constructed only on explicit use."""

    def __init__(self, timeout_seconds: float = 30.0):
        import httpx

        self._client = httpx.Client(
            follow_redirects=False,
            timeout=httpx.Timeout(timeout_seconds),
            headers={
                "User-Agent": "RomanPics-worker/0.1 (+https://github.com/Michionlion/romanpics)"
            },
        )

    def get(self, url: str) -> ResponseLike:
        return self.request("GET", url)

    def request(
        self, method: str, url: str, *, headers: Mapping[str, str] | None = None
    ) -> ResponseLike:
        request = self._client.build_request(method, url, headers=headers)
        return self._client.send(request, stream=True)

    def close(self) -> None:
        self._client.close()


class SafeRemoteFetcher:
    """Fetch with an allowlist, redirect validation, MIME checks, and a hard byte cap."""

    def __init__(
        self,
        policy: SourcePolicy,
        *,
        enabled: bool = False,
        transport: Transport | None = None,
        resolver: Callable[[str], Iterable[str]] = system_resolver,
    ):
        self.policy = policy
        self.enabled = enabled
        self._transport = transport
        self._owns_transport = transport is None
        self._resolver = resolver

    def __enter__(self) -> SafeRemoteFetcher:
        return self

    def __exit__(self, *_exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        if self._transport is not None and self._owns_transport:
            self._transport.close()
            self._transport = None

    def _get_transport(self) -> Transport:
        if not self.enabled:
            raise NetworkDisabledError("network fetching is disabled; construct with enabled=True")
        if not self.policy.allowed_hosts:
            raise SourceValidationError("at least one source host must be explicitly allowlisted")
        if self._transport is None:
            self._transport = HttpxTransport()
        return self._transport

    def _validate_resolution(self, url: str) -> None:
        host = urlsplit(url).hostname
        if not host:
            raise SourceValidationError("source URL has no hostname")
        try:
            addresses = list(self._resolver(host))
        except (OSError, socket.gaierror) as error:
            raise SourceValidationError(f"source host {host!r} could not be resolved") from error
        if not addresses:
            raise SourceValidationError(f"source host {host!r} resolved to no addresses")
        for address in addresses:
            try:
                parsed = ipaddress.ip_address(address.split("%", 1)[0])
            except ValueError as error:
                raise SourceValidationError(
                    f"resolver returned invalid address {address!r}"
                ) from error
            if not parsed.is_global:
                raise SourceValidationError(
                    f"source host {host!r} resolved to non-public address {parsed.compressed!r}"
                )

    def _open_validated_response(self, url: str) -> tuple[ResponseLike, str, tuple[str, ...]]:
        transport = self._get_transport()
        requested = self.policy.validate_url(url)
        current = requested
        redirects: list[str] = []
        for _ in range(self.policy.max_redirects + 1):
            # Resolve again for every hop. Production transports should additionally
            # pin their connection to the checked address when the threat model
            # includes a compromised public allowlist domain.
            self._validate_resolution(current)
            response = transport.get(current)
            if response.status_code in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                response.close()
                if not location:
                    raise SourceValidationError(
                        "redirect response did not provide a Location header"
                    )
                if len(redirects) >= self.policy.max_redirects:
                    raise SourceValidationError("source exceeded the redirect limit")
                current = self.policy.validate_url(urljoin(current, location))
                redirects.append(current)
                continue
            if response.status_code < 200 or response.status_code >= 300:
                response.close()
                raise SourceValidationError(f"source returned HTTP {response.status_code}")
            return response, current, tuple(redirects)
        raise SourceValidationError("source exceeded the redirect limit")

    def probe(self, url: str) -> ProbeMetadata:
        """Check an allowlisted URL without consuming its body.

        HEAD is preferred. Servers that reject HEAD receive a one-byte range GET;
        that response is closed without iterating its stream.
        """

        transport = self._get_transport()
        requested = self.policy.validate_url(url)
        current = requested
        redirects: list[str] = []
        method = "HEAD"
        for _ in range(self.policy.max_redirects + 2):
            self._validate_resolution(current)
            request = getattr(transport, "request", None)
            if request is None:
                if method != "GET":
                    raise RuntimeError("configured transport does not support safe HEAD probes")
                response = transport.get(current)
            else:
                headers = {"Range": "bytes=0-0"} if method == "GET" else None
                response = request(method, current, headers=headers)
            status = response.status_code
            if status in {301, 302, 303, 307, 308}:
                location = response.headers.get("location")
                response.close()
                if not location:
                    raise SourceValidationError(
                        "redirect response did not provide a Location header"
                    )
                if len(redirects) >= self.policy.max_redirects:
                    raise SourceValidationError("source exceeded the redirect limit")
                current = self.policy.validate_url(urljoin(current, location))
                redirects.append(current)
                method = "HEAD"
                continue
            if status in {403, 405} and method == "HEAD":
                response.close()
                method = "GET"
                continue
            response.close()
            if status < 200 or status >= 400:
                raise SourceValidationError(f"source returned HTTP {status}")
            return ProbeMetadata(
                requested_url=requested,
                final_url=current,
                status_code=status,
                redirects=tuple(redirects),
            )
        raise SourceValidationError("source exceeded the redirect limit")

    def fetch_bytes(self, url: str) -> tuple[bytes, FetchMetadata]:
        requested = self.policy.validate_url(url)
        response, final_url, redirects = self._open_validated_response(requested)
        try:
            raw_content_type = response.headers.get("content-type", "")
            content_type = raw_content_type.split(";", 1)[0].strip().lower()
            if content_type not in self.policy.allowed_mime_types:
                raise SourceValidationError(
                    f"source MIME type {content_type or '<missing>'!r} is not allowed"
                )
            length_header = response.headers.get("content-length")
            if length_header:
                try:
                    declared_length = int(length_header)
                except ValueError as error:
                    raise SourceValidationError("source Content-Length is invalid") from error
                if declared_length < 0 or declared_length > self.policy.max_bytes:
                    raise SourceValidationError("source exceeds the configured byte limit")
            chunks: list[bytes] = []
            size = 0
            for chunk in response.iter_bytes():
                size += len(chunk)
                if size > self.policy.max_bytes:
                    raise SourceValidationError(
                        "source exceeded the configured byte limit while streaming"
                    )
                chunks.append(chunk)
            return b"".join(chunks), FetchMetadata(
                requested_url=requested,
                final_url=final_url,
                content_type=content_type,
                size=size,
                redirects=redirects,
            )
        finally:
            response.close()

    @contextlib.contextmanager
    def temporary_file(
        self, url: str, *, parent: str | Path | None = None
    ) -> Iterator[tuple[Path, FetchMetadata]]:
        """Yield a fetched file and remove the complete temporary directory afterward."""

        payload, metadata = self.fetch_bytes(url)
        suffix_by_type = {
            "application/fits": ".fits",
            "application/x-fits": ".fits",
            "image/fits": ".fits",
            "application/asdf": ".asdf",
            "application/x-asdf": ".asdf",
            "image/jpeg": ".jpg",
            "image/png": ".png",
            "image/webp": ".webp",
        }
        suffix = suffix_by_type.get(
            metadata.content_type, Path(urlsplit(metadata.final_url).path).suffix
        )
        with tempfile.TemporaryDirectory(prefix="romanpics-fetch-", dir=parent) as temp_dir:
            path = Path(temp_dir) / f"source{suffix}"
            path.write_bytes(payload)
            yield path, metadata
