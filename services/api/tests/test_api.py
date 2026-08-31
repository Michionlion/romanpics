from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy import func, select

from romanpics_api.main import create_app
from romanpics_api.models import ActiveVote, VoteEvent


def test_public_read_contract_and_stable_seed(client):
    response = client.get("/v1/items?limit=3")
    assert response.status_code == 200
    assert response.headers["etag"].startswith('"')
    cached = client.get("/v1/items?limit=3", headers={"If-None-Match": response.headers["etag"]})
    assert cached.status_code == 304
    assert cached.content == b""
    body = response.json()
    assert body["total_estimate"] == 8
    assert len(body["data"]) == 3
    assert body["next_cursor"]
    assert all(item["source"]["source_url"].startswith("https://") for item in body["data"])
    assert all(item["content_class"] != "FLIGHT_SCIENCE" for item in body["data"])

    detail = client.get("/v1/items/launch-day")
    assert detail.status_code == 200
    assert detail.json()["id"] == "4c263736-41ed-5918-abac-8edf0bd38db8"
    assert detail.json()["originals"][0]["url"].startswith("https://images-assets.nasa.gov/")

    second_page = client.get("/v1/items", params={"cursor": body["next_cursor"], "limit": 3})
    assert second_page.status_code == 200
    assert not (
        {item["id"] for item in body["data"]} & {item["id"] for item in second_page.json()["data"]}
    )
    numbered_page = client.get("/v1/items", params={"page": 2, "limit": 3})
    assert numbered_page.json()["data"] == second_page.json()["data"]
    assert (
        client.get("/v1/items", params={"cursor": body["next_cursor"], "page": 2}).status_code
        == 400
    )
    assert client.get("/v1/items", params={"tag": "galaxies"}).json()["total_estimate"] > 0


def test_discovery_routes(client):
    assert client.get("/v1/items/beauty-pass/similar").json()["data"]
    assert client.get("/v1/items/beauty-pass/products").json()["data"]
    assert client.get("/v1/clusters").json()["total_estimate"] == 3
    assert len(client.get("/v1/clusters/cosmic-simulations").json()["members"]) == 2
    assert len(client.get("/v1/collections/road-to-first-light").json()["items"]) == 3
    collections = client.get("/v1/collections")
    assert collections.status_code == 200
    assert {row["slug"] for row in collections.json()["data"]} == {
        "building-roman",
        "road-to-first-light",
        "what-roman-may-see",
    }
    assert client.get("/v1/search/suggest", params={"q": "gal"}).json()["data"]
    facets = client.get("/v1/facets").json()
    assert {row["value"] for row in facets["content_class"]} == {
        "MISSION_PHOTO",
        "SIMULATION",
        "VISUALIZATION",
    }
    assert client.get("/v1/sources/status").json()["data"][0]["state"] == "healthy"
    for mode in ("anything", "galaxies", "mission", "calm", "engineering"):
        surprise = client.get("/v1/surprise", params={"mode": mode})
        assert surprise.status_code == 200
        assert surprise.json()["mode"] == mode


def test_filters_and_problem_responses(client):
    response = client.get("/v1/items", params={"content_class": "SIMULATION"})
    assert response.status_code == 200
    assert {item["content_class"] for item in response.json()["data"]} == {"SIMULATION"}
    assert client.get("/v1/items", params={"q": "cleanroom"}).json()["total_estimate"] == 2

    malformed = client.get("/v1/items?cursor=this-is-not-a-cursor")
    assert malformed.status_code == 400
    assert malformed.headers["content-type"].startswith("application/problem+json")
    assert malformed.json()["status"] == 400
    incomplete_cone = client.get("/v1/items?ra=10")
    assert incomplete_cone.status_code == 400
    missing = client.get("/v1/items/not-a-real-slug")
    assert missing.status_code == 404
    assert missing.json()["type"].endswith("http-404")


def test_vote_is_unique_reversible_and_origin_checked(client, seeded_database):
    item_id = client.get("/v1/items/launch-day").json()["id"]
    path = f"/v1/me/votes/items/{item_id}"
    assert client.put(path).status_code == 403
    first = client.put(path, headers={"Origin": "https://app.test"})
    assert first.status_code == 200
    assert first.json()["vote_count"] == 1
    cookie = first.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=lax" in cookie

    duplicate = client.put(path, headers={"Origin": "https://app.test"})
    assert duplicate.json()["vote_count"] == 1
    personalized = client.get("/v1/items/launch-day")
    assert personalized.json()["viewer_has_voted"] is True
    assert personalized.headers["cache-control"] == "private, no-cache"
    assert "Cookie" in personalized.headers["vary"]
    removed = client.delete(path, headers={"Origin": "https://app.test"})
    assert removed.json() == {
        "target_kind": "item",
        "target_id": item_id,
        "viewer_has_voted": False,
        "vote_count": 0,
    }
    _, factory = seeded_database
    with factory() as session:
        assert session.scalar(select(func.count(ActiveVote.id))) == 0
        assert session.scalar(select(func.count(VoteEvent.id))) == 2


def test_vote_network_limit_survives_cookie_deletion(seeded_database, settings):
    engine, _ = seeded_database
    limited_settings = settings.model_copy(update={"rate_limit_votes_per_minute": 1})
    application = create_app(limited_settings, engine=engine)
    with TestClient(
        application,
        base_url="https://api.test",
        client=("203.0.113.42", 50000),
    ) as limited_client:
        item_id = limited_client.get("/v1/items/launch-day").json()["id"]
        path = f"/v1/me/votes/items/{item_id}"
        first = limited_client.put(path, headers={"Origin": "https://app.test"})
        assert first.status_code == 200
        limited_client.cookies.clear()
        second = limited_client.put(path, headers={"Origin": "https://app.test"})
        assert second.status_code == 429
        assert second.headers["content-type"].startswith("application/problem+json")


def test_openapi_uses_canonical_v1_paths(client):
    schema = client.get("/openapi.json").json()
    assert "/v1/surprise" in schema["paths"]
    assert "/v1/items" in schema["paths"]
    assert all(not path.startswith("/api/") for path in schema["paths"])
    operation_ids = {
        operation["operationId"]
        for path in schema["paths"].values()
        for operation in path.values()
        if isinstance(operation, dict) and "operationId" in operation
    }
    assert {"listItems", "getItem", "getSurprise", "addItemVote"} <= operation_ids
