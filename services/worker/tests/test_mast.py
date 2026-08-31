from __future__ import annotations

import json
from pathlib import Path

from romanpics_worker.mast import MastProductRegistry, extract_mast_rows

FIXTURES = Path(__file__).parent / "fixtures"


def rows(name: str):
    return extract_mast_rows(json.loads((FIXTURES / name).read_text()))


def test_prompt_uri_overwrite_creates_an_immutable_generation() -> None:
    registry = MastProductRegistry()
    key = "ROMAN-DEMO-001:WFI01:F158:L3-MOSAIC"
    created = registry.apply_rows(rows("mast_prompt_v1.json"), run_id="poll-1")
    overwritten = registry.apply_rows(rows("mast_prompt_v2.json"), run_id="poll-2")

    assert [event.kind for event in created] == ["created"]
    assert [event.kind for event in overwritten] == ["overwritten"]
    history = registry.history(key)
    assert [generation.generation for generation in history] == [1, 2]
    assert [generation.status for generation in history] == ["replaced", "active"]
    assert history[0].asset_uri == history[1].asset_uri
    assert history[0].content_token != history[1].content_token


def test_replaying_same_prompt_fixture_is_idempotent() -> None:
    registry = MastProductRegistry()
    registry.apply_rows(rows("mast_prompt_v2.json"), run_id="poll-1")
    replay = registry.apply_rows(rows("mast_prompt_v2.json"), run_id="poll-2")
    assert [event.kind for event in replay] == ["unchanged"]
    assert len(registry.active()) == 1
    assert len(registry.history(registry.active()[0].logical_key)) == 1


def test_final_product_supersedes_latest_prompt_generation() -> None:
    registry = MastProductRegistry()
    key = "ROMAN-DEMO-001:WFI01:F158:L3-MOSAIC"
    registry.apply_rows(rows("mast_prompt_v1.json"), run_id="poll-1")
    registry.apply_rows(rows("mast_prompt_v2.json"), run_id="poll-2")
    events = registry.apply_rows(rows("mast_final.json"), run_id="poll-final")
    assert [event.kind for event in events] == ["superseded"]
    history = registry.history(key)
    assert [generation.status for generation in history] == ["replaced", "superseded", "active"]
    assert history[-1].release_kind == "final"
    assert history[-2].superseded_by == history[-1].asset_uri


def test_metadata_only_change_does_not_create_a_generation() -> None:
    registry = MastProductRegistry()
    first = rows("mast_prompt_v1.json")[0]
    changed = {**first, "proposal_pi": "Grace Hopper"}
    registry.apply_rows([first], run_id="one")
    events = registry.apply_rows([changed], run_id="two")
    assert [event.kind for event in events] == ["metadata_updated"]
    assert len(registry.history(registry.active()[0].logical_key)) == 1
