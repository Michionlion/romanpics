from __future__ import annotations

import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from romanpics_api.config import Settings
from romanpics_api.database import build_engine, build_session_factory, create_schema
from romanpics_api.main import create_app
from romanpics_api.services.seed import seed_catalog


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return Settings(
        database_url=f"sqlite:///{tmp_path / 'test.db'}",
        visitor_signing_secret="test-signing-secret-that-is-long-enough",
        allowed_origins=("https://app.test",),
        cookie_secure=False,
        mast_fixture_enabled=True,
    )


@pytest.fixture
def database(settings: Settings):
    engine = build_engine(settings)
    create_schema(engine)
    factory = build_session_factory(engine)
    yield engine, factory
    engine.dispose()


@pytest.fixture
def seeded_database(database, settings: Settings):
    engine, factory = database
    fixture = Path(__file__).parents[1] / "manifests" / "reviewed.json"
    asyncio.run(seed_catalog(factory, fixture, settings.allowed_upstream_hosts))
    return engine, factory


@pytest.fixture
def client(seeded_database, settings: Settings):
    engine, _ = seeded_database
    with TestClient(
        create_app(settings, engine=engine), base_url="https://api.test"
    ) as test_client:
        yield test_client
