from __future__ import annotations

import httpx
import pytest

from romanpics_api.adapters import NasaImagesAdapter, NasaSvsAdapter


@pytest.mark.asyncio
async def test_nasa_images_search_assets_and_normalization():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/search":
            return httpx.Response(
                200,
                json={
                    "collection": {
                        "metadata": {"total_hits": 1},
                        "items": [
                            {
                                "data": [
                                    {
                                        "nasa_id": "ROMAN_001",
                                        "title": "Roman in a cleanroom",
                                        "description_508": "Technicians prepare Roman.",
                                        "date_created": "2026-01-01T00:00:00Z",
                                        "keywords": ["Roman", "cleanroom"],
                                        "photographer": "NASA Test Photographer",
                                    }
                                ],
                                "links": [
                                    {
                                        "href": "https://images-assets.nasa.gov/image/ROMAN_001/ROMAN_001~medium.jpg",
                                        "render": "image",
                                    }
                                ],
                            }
                        ],
                    }
                },
            )
        if request.url.path == "/asset/ROMAN_001":
            return httpx.Response(
                200,
                json={
                    "collection": {
                        "items": [
                            {
                                "href": "http://images-assets.nasa.gov/image/ROMAN_001/ROMAN_001~medium.jpg"
                            },
                            {
                                "href": "http://images-assets.nasa.gov/image/ROMAN_001/ROMAN_001~orig.jpg"
                            },
                        ]
                    }
                },
            )
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = NasaImagesAdapter(client)
        page = await adapter.discover()
        normalized = await adapter.normalize(page.records[0])
    assert page.next_cursor == "1:1"
    assert normalized.external_id == "ROMAN_001"
    assert normalized.content_class == "MISSION_PHOTO"
    assert normalized.products[0].url.endswith("~orig.jpg")
    assert normalized.products[0].url.startswith("https://images-assets.nasa.gov/")
    assert normalized.renditions[0].url.endswith("~medium.jpg")
    assert normalized.raw["asset_manifest"]


@pytest.mark.asyncio
async def test_svs_real_nested_media_shape_selects_searchweb_and_preserves_metadata():
    detail = {
        "id": 13921,
        "title": "Roman synthetic deep field",
        "description": "A simulation of galaxies Roman may observe.",
        "page_type": "Visualization",
        "release_date": "2024-02-03T00:00:00Z",
        "update_date": "2025-04-05T00:00:00Z",
        "page_url": "https://svs.gsfc.nasa.gov/13921/",
        "main_image": {
            "url": "https://svs.gsfc.nasa.gov/vis/full_print.jpg",
            "width": 4096,
            "height": 2160,
            "alt_text": "Thousands of simulated galaxies fill a dark field.",
        },
        "credits": [
            {"role": "Visualizer", "people": [{"name": "A. Person"}, {"name": "B. Person"}]}
        ],
        "media_groups": [
            {
                "items": [
                    {
                        "instance": [
                            {
                                "url": "https://svs.gsfc.nasa.gov/vis/full_searchweb.jpg",
                                "width": 320,
                                "height": 180,
                                "alt_text": "Compact simulated galaxy preview.",
                            },
                            {
                                "url": "https://svs.gsfc.nasa.gov/vis/full_1080.jpg",
                                "width": 1920,
                                "height": 1080,
                            },
                        ]
                    }
                ]
            }
        ],
    }

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/search/":
            return httpx.Response(200, json={"results": [{"id": 13921}], "next": None})
        if request.url.path == "/api/13921/":
            return httpx.Response(200, json=detail)
        return httpx.Response(404)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        adapter = NasaSvsAdapter(client)
        page = await adapter.discover()
        normalized = await adapter.normalize(page.records[0])
    assert normalized.content_class == "SIMULATION"
    assert normalized.renditions[0].url.endswith("_searchweb.jpg")
    assert (normalized.renditions[0].width, normalized.renditions[0].height) == (320, 180)
    assert normalized.products[0].url.endswith("full_print.jpg")
    assert normalized.alt_text == "Thousands of simulated galaxies fill a dark field."
    assert normalized.credit == "A. Person / B. Person"
    assert normalized.upstream_updated_at.year == 2025
