from __future__ import annotations

import pytest
from pydantic import ValidationError

from romanpics_api.config import Settings


def test_comma_separated_browser_origins(monkeypatch):
    monkeypatch.setenv("ALLOWED_ORIGINS", "https://one.test,https://two.test")
    assert Settings().allowed_origins == ("https://one.test", "https://two.test")


def test_cookie_security_configuration_rejects_unsafe_combinations():
    with pytest.raises(ValidationError):
        Settings(allowed_origins=("*",))
    with pytest.raises(ValidationError):
        Settings(cookie_samesite="none", cookie_secure=False)


def test_production_rejects_insecure_placeholders():
    with pytest.raises(ValidationError, match="production requires"):
        Settings(
            environment="production",
            visitor_signing_secret="replace-with-at-least-32-random-bytes",
            public_base_url="http://example.test",
            allowed_origins=("http://example.test",),
        )


def test_production_accepts_https_and_random_secret():
    value = Settings(
        environment="production",
        visitor_signing_secret="1df26f8e9b6bd86ced99afae95bbf4389131d48bf532b003c4c456e741d888e7",
        public_base_url="https://romanpics.example",
        allowed_origins=("https://romanpics.example",),
    )
    assert value.cookie_secure is True
