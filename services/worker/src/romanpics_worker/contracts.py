"""Runtime validation for the backend's jobs-v1 contract."""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping
from typing import Any, Literal, TypedDict, cast

JobType = Literal["render", "embed", "cluster", "link-check"]
JOB_TYPES: tuple[JobType, ...] = ("render", "embed", "cluster", "link-check")


class RenderPayload(TypedDict):
    item_id: str
    product_id: str
    recipe: dict[str, Any]


class EmbedPayload(TypedDict):
    item_id: str
    source_record_id: str
    checksum: str


class ClusterPayload(TypedDict):
    source_id: str
    ingest_run_id: str


class LinkCheckPayload(TypedDict):
    scope: str


JobPayload = RenderPayload | EmbedPayload | ClusterPayload | LinkCheckPayload


class JobContractError(ValueError):
    """A queued or submitted job does not satisfy jobs-v1."""


_CHECKSUM = re.compile(r"^[a-f0-9]{64}$")


def _uuid(value: object, field: str) -> str:
    if not isinstance(value, str):
        raise JobContractError(f"{field} must be a UUID string")
    try:
        parsed = uuid.UUID(value)
    except (ValueError, AttributeError) as error:
        raise JobContractError(f"{field} must be a UUID string") from error
    if str(parsed) != value.lower():
        raise JobContractError(f"{field} must use canonical UUID form")
    return value


def _json_value(value: Any, path: str = "recipe") -> Any:
    if value is None or isinstance(value, str | int | float | bool):
        return value
    if isinstance(value, list):
        return [_json_value(item, f"{path}[]") for item in value]
    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise JobContractError(f"{path} keys must be strings")
            output[key] = _json_value(item, f"{path}.{key}")
        return output
    raise JobContractError(f"{path} must contain only JSON values")


def _exact_keys(payload: Mapping[str, Any], expected: set[str]) -> None:
    keys = set(payload)
    missing = expected - keys
    extra = keys - expected
    if missing:
        raise JobContractError(f"missing payload fields: {', '.join(sorted(missing))}")
    if extra:
        raise JobContractError(f"unexpected payload fields: {', '.join(sorted(extra))}")


def validate_job_payload(job_type: str, payload: Mapping[str, Any]) -> JobPayload:
    """Validate and copy one of the four backend-defined payload shapes."""

    if job_type not in JOB_TYPES:
        raise JobContractError(f"unsupported job type {job_type!r}")
    if not isinstance(payload, Mapping):
        raise JobContractError("payload_json must be an object")

    if job_type == "render":
        _exact_keys(payload, {"item_id", "product_id", "recipe"})
        recipe = payload["recipe"]
        if not isinstance(recipe, Mapping):
            raise JobContractError("recipe must be an object")
        return RenderPayload(
            item_id=_uuid(payload["item_id"], "item_id"),
            product_id=_uuid(payload["product_id"], "product_id"),
            recipe=cast(dict[str, Any], _json_value(recipe)),
        )
    if job_type == "embed":
        _exact_keys(payload, {"item_id", "source_record_id", "checksum"})
        checksum = payload["checksum"]
        if not isinstance(checksum, str) or not _CHECKSUM.fullmatch(checksum):
            raise JobContractError("checksum must be 64 lowercase hexadecimal characters")
        return EmbedPayload(
            item_id=_uuid(payload["item_id"], "item_id"),
            source_record_id=_uuid(payload["source_record_id"], "source_record_id"),
            checksum=checksum,
        )
    if job_type == "cluster":
        _exact_keys(payload, {"source_id", "ingest_run_id"})
        return ClusterPayload(
            source_id=_uuid(payload["source_id"], "source_id"),
            ingest_run_id=_uuid(payload["ingest_run_id"], "ingest_run_id"),
        )

    _exact_keys(payload, {"scope"})
    scope = payload["scope"]
    if not isinstance(scope, str) or not scope.strip():
        raise JobContractError("scope must be a non-empty string")
    return LinkCheckPayload(scope=scope)
