from __future__ import annotations

import re
import unicodedata
from datetime import UTC, date, datetime
from html import unescape
from typing import Any

_TAG_RE = re.compile(r"<[^>]+>")
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def clean_text(value: Any, fallback: str = "") -> str:
    if value is None:
        return fallback
    text = unescape(_TAG_RE.sub(" ", str(value)))
    return " ".join(text.split()) or fallback


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode()
    return _SLUG_RE.sub("-", normalized.lower()).strip("-")[:240] or "untitled"


def parse_datetime(value: Any) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day, tzinfo=UTC)
    text = str(value).strip().replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%d %B %Y"):
            try:
                parsed = datetime.strptime(text, fmt).replace(tzinfo=UTC)
                break
            except ValueError:
                continue
        else:
            return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def content_type_from_url(url: str) -> str:
    path = url.lower().split("?", 1)[0]
    return {
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".png": "image/png",
        ".webp": "image/webp",
        ".gif": "image/gif",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
        ".asdf": "application/x-asdf",
        ".fits": "application/fits",
        ".fit": "application/fits",
    }.get(
        next(
            (
                ext
                for ext in (
                    ".jpeg",
                    ".tiff",
                    ".webp",
                    ".fits",
                    ".asdf",
                    ".jpg",
                    ".png",
                    ".gif",
                    ".tif",
                    ".fit",
                )
                if path.endswith(ext)
            ),
            "",
        ),
        "application/octet-stream",
    )
