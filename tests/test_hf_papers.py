"""Parser HF Daily Papers, chạy trên response thật đã ghi lại (không cần mạng)."""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from ai_radar.collectors.hf_papers import API_URL, HFDailyPapersCollector
from ai_radar.http import FetchError, build_client
from ai_radar.models import Kind

FIXTURE = Path(__file__).parent / "fixtures" / "hf_daily_papers.json"
DAY = date(2026, 7, 31)


@pytest.fixture
def payload() -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads(FIXTURE.read_text(encoding="utf-8"))
    return data


async def _fetch(payload: Any, status: int = 200) -> list[Any]:
    with respx.mock:
        respx.get(API_URL).mock(return_value=httpx.Response(status, json=payload))
        async with build_client() as client:
            return await HFDailyPapersCollector().fetch(client, DAY)


async def test_parses_every_fixture_record(payload: list[dict[str, Any]]) -> None:
    items = await _fetch(payload)
    assert len(items) == len(payload)
    assert all(i.kind is Kind.PAPER for i in items)
    assert all(i.title and i.id and i.summary_en for i in items)


async def test_builds_hf_and_arxiv_links(payload: list[dict[str, Any]]) -> None:
    item = next(i for i in await _fetch(payload) if i.title.startswith("OmniScope"))
    sources = {link.source: link.url for link in item.links}
    assert sources["hf_papers"] == "https://huggingface.co/papers/2607.23193"
    assert sources["arxiv"] == "https://arxiv.org/abs/2607.23193"
    assert "github.com/MAC-AutoML/OmniScope" in sources["github"]


async def test_missing_github_repo_is_not_an_error(payload: list[dict[str, Any]]) -> None:
    """githubRepo chỉ có ở ~64% record — thiếu là bình thường, không phải lỗi."""
    items = await _fetch(payload)
    without = [i for i in items if not any(link.source == "github" for link in i.links)]
    assert without, "fixture phải có record không kèm GitHub"
    assert all(i.signals.has_code is False for i in without)
    assert all(i.signals.github_stars == 0 for i in without)


async def test_zero_upvotes_is_preserved_not_dropped(payload: list[dict[str, Any]]) -> None:
    items = await _fetch(payload)
    assert any(i.signals.hf_upvotes == 0 for i in items)
    assert all(i.signals.is_daily_paper for i in items)


async def test_dedup_keys_include_arxiv_and_title(payload: list[dict[str, Any]]) -> None:
    item = (await _fetch(payload))[0]
    assert any(k.startswith("arxiv:") for k in item.dedup_keys)
    assert any(k.startswith("title:") for k in item.dedup_keys)


async def test_one_broken_record_does_not_lose_the_batch(
    payload: list[dict[str, Any]],
) -> None:
    """Record thiếu `id` bị bỏ qua, các record còn lại vẫn về đủ."""
    broken = [{"paper": {"title": "thiếu id"}}, *payload]
    items = await _fetch(broken)
    assert len(items) == len(payload)


async def test_non_list_payload_raises() -> None:
    with pytest.raises(TypeError):
        await _fetch({"error": "rate limited"})


async def test_persistent_5xx_raises_fetch_error() -> None:
    with respx.mock:
        respx.get(API_URL).mock(return_value=httpx.Response(503))
        async with build_client() as client:
            with pytest.raises(FetchError):
                await HFDailyPapersCollector().fetch(client, DAY)


async def test_retries_then_succeeds(payload: list[dict[str, Any]]) -> None:
    """503 tạm thời phải được retry chứ không làm mất nguồn."""
    with respx.mock:
        route = respx.get(API_URL)
        route.side_effect = [
            httpx.Response(503),
            httpx.Response(200, json=payload),
        ]
        async with build_client() as client:
            items = await HFDailyPapersCollector().fetch(client, DAY)
    assert len(items) == len(payload)
