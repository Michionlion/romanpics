"""Storage-neutral publication of generated preview objects."""

from __future__ import annotations

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Protocol
from urllib.parse import quote, unquote, urlsplit


@dataclass(frozen=True)
class StoredPreview:
    key: str
    storage_uri: str
    public_url: str | None
    content_type: str
    size: int
    sha256: str


class PreviewStore(Protocol):
    def put_file(
        self, key: str, source: str | Path, *, content_type: str = "image/webp"
    ) -> StoredPreview: ...

    def read_public_url(self, url: str) -> bytes | None: ...


def _safe_key(key: str) -> PurePosixPath:
    path = PurePosixPath(key)
    if not key or path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("preview storage key must be a safe relative POSIX path")
    return path


class LocalPreviewStore:
    """Atomic filesystem storage with an optional, explicitly configured public URL."""

    def __init__(self, root: str | Path, *, public_base_url: str | None = None):
        self.root = Path(root)
        self.public_base_url = public_base_url.rstrip("/") if public_base_url else None

    def put_file(
        self, key: str, source: str | Path, *, content_type: str = "image/webp"
    ) -> StoredPreview:
        safe = _safe_key(key)
        payload = Path(source).read_bytes()
        digest = hashlib.sha256(payload).hexdigest()
        destination = self.root.joinpath(*safe.parts)
        destination.parent.mkdir(parents=True, exist_ok=True)
        if not destination.exists() or destination.read_bytes() != payload:
            file_descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{destination.name}.", suffix=".tmp", dir=destination.parent
            )
            temporary = Path(temporary_name)
            try:
                with os.fdopen(file_descriptor, "wb") as output:
                    output.write(payload)
                    output.flush()
                    os.fsync(output.fileno())
                temporary.replace(destination)
            finally:
                temporary.unlink(missing_ok=True)
        encoded_key = "/".join(quote(part, safe="") for part in safe.parts)
        return StoredPreview(
            key=str(safe),
            storage_uri=f"local://{encoded_key}",
            public_url=f"{self.public_base_url}/{encoded_key}" if self.public_base_url else None,
            content_type=content_type,
            size=len(payload),
            sha256=digest,
        )

    def read_public_url(self, url: str) -> bytes | None:
        """Read a URL owned by this store without a public-network round trip.

        A generated rendition is saved in the same mounted preview volume that the
        worker later embeds. Mapping it back through the configured public URL keeps
        that second stage independent of DNS, TLS, proxy availability, and upstream
        host allowlists. Only exact-origin URLs beneath the configured base path are
        accepted; encoded separators, traversal, queries, fragments, and symlinks
        escaping the preview root are rejected.
        """

        if self.public_base_url is None:
            return None
        base = urlsplit(self.public_base_url)
        candidate = urlsplit(url)
        if (
            base.scheme.lower() != "https"
            or candidate.scheme.lower() != "https"
            or candidate.netloc.lower() != base.netloc.lower()
            or candidate.query
            or candidate.fragment
        ):
            return None
        base_parts = tuple(part for part in base.path.split("/") if part)
        candidate_parts = tuple(part for part in candidate.path.split("/") if part)
        if candidate_parts[: len(base_parts)] != base_parts:
            return None
        raw_relative = candidate_parts[len(base_parts) :]
        if not raw_relative:
            return None
        decoded: list[str] = []
        for raw_part in raw_relative:
            part = unquote(raw_part)
            if not part or part in {".", ".."} or "/" in part or "\\" in part:
                return None
            decoded.append(part)
        safe = _safe_key("/".join(decoded))
        root = self.root.resolve()
        target = self.root.joinpath(*safe.parts).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            return None
        return target.read_bytes()
