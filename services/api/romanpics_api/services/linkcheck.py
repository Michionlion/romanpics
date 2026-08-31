from __future__ import annotations

import asyncio
import ipaddress
import socket
from collections.abc import Iterable
from dataclasses import dataclass
from urllib.parse import urljoin, urlsplit

import httpx
from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from ..models import ArchiveProduct, LinkCheck, Rendition, SourceRecord
from .security import url_host_allowed


@dataclass(slots=True)
class LinkTarget:
    url: str
    target_kind: str
    target_id: str


async def check_catalog_links(
    session_factory: sessionmaker[Session],
    allowed_hosts: tuple[str, ...],
    *,
    timeout: float = 10.0,
    client: httpx.AsyncClient | None = None,
    resolve_dns: bool = True,
    limit: int | None = None,
) -> dict[str, int]:
    session = session_factory()
    targets = list(_targets(session))[:limit]
    session.close()
    owns_client = client is None
    client = client or httpx.AsyncClient(
        timeout=timeout,
        follow_redirects=False,
        headers={"User-Agent": "RomanPics-LinkChecker/0.1"},
    )
    ok = 0
    failed = 0
    try:
        for target in targets:
            result = await _check_one(client, target.url, allowed_hosts, resolve_dns)
            session = session_factory()
            session.add(
                LinkCheck(
                    url=target.url,
                    target_kind=target.target_kind,
                    target_id=target.target_id,
                    ok=result[0],
                    status_code=result[1],
                    final_url=result[2],
                    error=result[3],
                )
            )
            session.commit()
            session.close()
            if result[0]:
                ok += 1
            else:
                failed += 1
    finally:
        if owns_client:
            await client.aclose()
    return {"checked": len(targets), "ok": ok, "failed": failed}


def _targets(session: Session) -> Iterable[LinkTarget]:
    seen: set[str] = set()
    for model, column, kind in (
        (SourceRecord, SourceRecord.canonical_url, "source_record"),
        (Rendition, Rendition.url, "rendition"),
        (ArchiveProduct, ArchiveProduct.external_url, "archive_product"),
    ):
        for target_id, url in session.execute(select(model.id, column)).all():
            if url not in seen:
                seen.add(url)
                yield LinkTarget(url=url, target_kind=kind, target_id=target_id)


async def _check_one(
    client: httpx.AsyncClient,
    url: str,
    allowed_hosts: tuple[str, ...],
    resolve_dns: bool,
) -> tuple[bool, int | None, str | None, str | None]:
    try:
        if not url_host_allowed(url, allowed_hosts):
            raise ValueError("URL host is not allowlisted")
        if resolve_dns:
            await _assert_public_dns(url)
        current = url
        method = "HEAD"
        for _hop in range(6):
            if not url_host_allowed(current, allowed_hosts):
                raise ValueError("redirect escaped the upstream allowlist")
            if resolve_dns:
                await _assert_public_dns(current)
            request = client.build_request(
                method,
                current,
                headers={"Range": "bytes=0-0"} if method == "GET" else None,
            )
            response = await client.send(request, stream=True, follow_redirects=False)
            status = response.status_code
            location = response.headers.get("location")
            response_url = str(response.url)
            await response.aclose()  # never consume an upstream original body
            if status in {301, 302, 303, 307, 308}:
                if not location:
                    raise ValueError("redirect response had no Location header")
                current = urljoin(response_url, location)
                if status == 303:
                    method = "HEAD"
                continue
            if status in {403, 405} and method == "HEAD":
                method = "GET"
                continue
            response.raise_for_status()
            return True, status, response_url, None
        raise ValueError("too many upstream redirects")
    except Exception as exc:
        status = exc.response.status_code if isinstance(exc, httpx.HTTPStatusError) else None
        final = str(exc.response.url) if isinstance(exc, httpx.HTTPStatusError) else None
        return False, status, final, str(exc)[:2_000]


async def _assert_public_dns(url: str) -> None:
    host = urlsplit(url).hostname
    if not host:
        raise ValueError("URL has no hostname")
    loop = asyncio.get_running_loop()
    addresses = await loop.run_in_executor(
        None, lambda: socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    )
    for address in {entry[4][0] for entry in addresses}:
        ip = ipaddress.ip_address(address)
        if not ip.is_global:
            raise ValueError(f"upstream DNS resolved to a non-public address: {ip}")
