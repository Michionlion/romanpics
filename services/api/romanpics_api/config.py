from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal
from urllib.parse import urlparse

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration.

    PostgreSQL is the deployment target. SQLite is deliberately supported for
    tests and a zero-dependency local demo.
    """

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore"
    )

    app_name: str = "RomanPics API"
    environment: str = "development"
    database_url: str = "sqlite:///./romanpics.db"
    visitor_signing_secret: str = "development-only-secret-change-before-production"
    public_base_url: str = "http://localhost:3000"
    allowed_origins: Annotated[tuple[str, ...], NoDecode] = (
        "http://localhost:3000",
        "http://localhost:8000",
    )
    cookie_name: str = "romanpics_visitor"
    cookie_secure: bool = True
    cookie_samesite: Literal["lax", "strict", "none"] = "lax"
    cookie_max_age_seconds: int = 60 * 60 * 24 * 365
    manifest_path: Path = Path("manifests/reviewed.json")
    mast_fixture_enabled: bool = False
    max_sync_pages: int = Field(default=25, ge=1, le=500)
    rate_limit_votes_per_minute: int = Field(default=30, ge=1, le=1_000)
    link_check_timeout_seconds: float = Field(default=10.0, gt=0, le=60)
    allowed_upstream_hosts: Annotated[tuple[str, ...], NoDecode] = (
        "images.nasa.gov",
        "images-api.nasa.gov",
        "images-assets.nasa.gov",
        "svs.gsfc.nasa.gov",
        "archive.stsci.edu",
        "mast.stsci.edu",
        "irsa.ipac.caltech.edu",
        "roman.ipac.caltech.edu",
    )

    @field_validator("allowed_origins", "allowed_upstream_hosts", mode="before")
    @classmethod
    def parse_csv_tuple(cls, value: object) -> object:
        if isinstance(value, str) and not value.strip().startswith("["):
            return tuple(part.strip() for part in value.split(",") if part.strip())
        return value

    @field_validator("visitor_signing_secret")
    @classmethod
    def require_production_secret(cls, value: str, info: object) -> str:
        # The model-level production checks below are stricter. Keeping this first
        # validator permissive lets local CLI commands run without hidden setup.
        if len(value) < 16:
            raise ValueError("visitor_signing_secret must contain at least 16 characters")
        return value

    @model_validator(mode="after")
    def validate_browser_security(self) -> Settings:
        if "*" in self.allowed_origins:
            raise ValueError("wildcard origins are forbidden when cookies use credentials")
        if self.cookie_samesite == "none" and not self.cookie_secure:
            raise ValueError("SameSite=None requires Secure cookies")
        if self.environment.lower() == "production":
            unsafe_markers = ("development", "replace-with", "change-me")
            if len(self.visitor_signing_secret) < 32 or any(
                marker in self.visitor_signing_secret.lower() for marker in unsafe_markers
            ):
                raise ValueError(
                    "production requires a random visitor_signing_secret of 32+ characters"
                )
            if not self.cookie_secure:
                raise ValueError("production requires Secure visitor cookies")
            if urlparse(self.public_base_url).scheme != "https":
                raise ValueError("production public_base_url must use HTTPS")
            if any(urlparse(origin).scheme != "https" for origin in self.allowed_origins):
                raise ValueError("production allowed_origins must use HTTPS")
        return self


@lru_cache
def get_settings() -> Settings:
    return Settings()
