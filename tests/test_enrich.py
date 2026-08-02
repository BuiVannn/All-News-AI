"""Tầng enrich (tier-2).

Nguyên tắc xuyên suốt: **enrich lỗi không được làm hỏng lượt chạy**. Item vẫn
lên feed, chỉ thiếu tóm tắt. Vì vậy phần lớn test ở đây là về đường thất bại.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import httpx
import pytest
import respx

from ai_radar.enrich.base import NullEnricher
from ai_radar.enrich.gemini import API_URL, GeminiEnricher, _find_text, _parse_topics
from ai_radar.http import build_client
from ai_radar.models import Item, Kind, Topic


def make(title: str = "Sparse Routing for Long Context", summary: str | None = "Abstract") -> Item:
    now = datetime(2026, 7, 31, tzinfo=UTC)
    return Item(
        id="x",
        kind=Kind.PAPER,
        title=title,
        summary_en=summary,
        published_at=now,
        first_seen_at=now,
    )


def reply(**fields: Any) -> httpx.Response:
    body = {
        "summary_vi": "Bài này giới thiệu sparse routing giúp truy hồi tốt hơn ở ngữ cảnh dài.",
        "why_it_matters": "Giảm chi phí decode cho ứng dụng ngữ cảnh dài.",
        "topics": ["llm", "rag"],
        **fields,
    }
    return httpx.Response(200, json={"output_text": json.dumps(body, ensure_ascii=False)})


async def _run(enricher: GeminiEnricher, items: list[Item]) -> Any:
    async with build_client() as client:
        return await enricher.enrich(client, items)


@pytest.fixture
def enricher() -> GeminiEnricher:
    return GeminiEnricher(api_key="test-key", model="gemini-2.5-flash-lite")


# --------------------------------------------------------------------------
# Đường thành công
# --------------------------------------------------------------------------


async def test_fills_vietnamese_fields(enricher: GeminiEnricher) -> None:
    item = make()
    with respx.mock:
        respx.post(API_URL).mock(return_value=reply())
        result = await _run(enricher, [item])

    assert result.enriched == 1
    assert item.summary_vi and "sparse routing" in item.summary_vi.lower()
    assert item.why_it_matters
    assert item.topics == [Topic.LLM, Topic.RAG]


async def test_sends_key_revision_and_schema(enricher: GeminiEnricher) -> None:
    with respx.mock:
        route = respx.post(API_URL).mock(return_value=reply())
        await _run(enricher, [make()])

    request = route.calls[0].request
    assert request.headers["x-goog-api-key"] == "test-key"
    assert request.headers["Api-Revision"]  # pin phiên bản API

    body = json.loads(request.content)
    assert body["model"] == "gemini-2.5-flash-lite"
    assert body["response_format"]["mime_type"] == "application/json"
    assert "summary_vi" in body["response_format"]["schema"]["properties"]


async def test_prompt_includes_title_and_abstract(enricher: GeminiEnricher) -> None:
    with respx.mock:
        route = respx.post(API_URL).mock(return_value=reply())
        await _run(enricher, [make(title="Tiêu đề X", summary="Nội dung Y")])

    body = json.loads(route.calls[0].request.content)
    assert "Tiêu đề X" in body["input"]
    assert "Nội dung Y" in body["input"]


async def test_already_enriched_items_are_skipped(enricher: GeminiEnricher) -> None:
    """Chạy lại không được đốt thêm quota — cron chạy 2 lần/ngày."""
    item = make()
    item.summary_vi = "Đã có sẵn"

    with respx.mock:
        route = respx.post(API_URL).mock(return_value=reply())
        result = await _run(enricher, [item])

    assert result.requested == 0
    assert len(route.calls) == 0
    assert item.summary_vi == "Đã có sẵn"


# --------------------------------------------------------------------------
# Đường thất bại — quan trọng hơn
# --------------------------------------------------------------------------


async def test_http_error_leaves_item_usable(enricher: GeminiEnricher) -> None:
    """Nhà cung cấp lỗi thì item vẫn lên feed, chỉ thiếu tóm tắt."""
    item = make()
    with respx.mock:
        respx.post(API_URL).mock(return_value=httpx.Response(429, text="quota exceeded"))
        result = await _run(enricher, [item])

    assert result.failed == 1
    assert result.enriched == 0
    assert item.summary_vi is None
    assert item.title  # item vẫn nguyên vẹn


async def test_malformed_json_is_survived(enricher: GeminiEnricher) -> None:
    with respx.mock:
        respx.post(API_URL).mock(
            return_value=httpx.Response(200, json={"output_text": "không phải json"})
        )
        result = await _run(enricher, [make()])
    assert result.failed == 1


async def test_empty_summary_counts_as_failure(enricher: GeminiEnricher) -> None:
    item = make()
    with respx.mock:
        respx.post(API_URL).mock(return_value=reply(summary_vi="   "))
        result = await _run(enricher, [item])

    assert result.failed == 1
    assert item.summary_vi is None


async def test_one_failure_does_not_block_the_others(enricher: GeminiEnricher) -> None:
    good, bad = make(title="Tốt"), make(title="Hỏng")
    with respx.mock:
        respx.post(API_URL).mock(
            side_effect=[httpx.Response(500), reply()]
        )
        result = await _run(enricher, [bad, good])

    assert result.enriched == 1
    assert result.failed == 1


async def test_invalid_topic_is_dropped_not_fatal(enricher: GeminiEnricher) -> None:
    """Model bịa tag mới thì bỏ tag đó, không làm hỏng cả item."""
    item = make()
    with respx.mock:
        respx.post(API_URL).mock(return_value=reply(topics=["llm", "quantum-blockchain"]))
        result = await _run(enricher, [item])

    assert result.enriched == 1
    assert item.topics == [Topic.LLM]


# --------------------------------------------------------------------------
# Không cấu hình nhà cung cấp
# --------------------------------------------------------------------------


async def test_null_enricher_needs_no_network() -> None:
    item = make()
    async with build_client() as client:
        result = await NullEnricher().enrich(client, [item])

    assert result.provider == "none"
    assert result.skipped == 1
    assert item.summary_vi is None


def test_build_enricher_falls_back_without_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Không có key -> NullEnricher, không phải crash."""
    from ai_radar.enrich import build_enricher

    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    assert isinstance(build_enricher(), NullEnricher)


def test_build_enricher_uses_gemini_when_key_present(monkeypatch: pytest.MonkeyPatch) -> None:
    from ai_radar.enrich import build_enricher

    monkeypatch.setenv("GEMINI_API_KEY", "abc")
    assert isinstance(build_enricher(), GeminiEnricher)


# --------------------------------------------------------------------------
# Hàm phụ
# --------------------------------------------------------------------------


def test_find_text_handles_both_response_shapes() -> None:
    """`output_text` là đường chính; shape lồng là đường lui nếu REST khác SDK."""
    assert _find_text({"output_text": "xin chào"}) == "xin chào"
    assert _find_text({"output": [{"content": [{"text": "lồng"}]}]}) == "lồng"
    assert _find_text({"candidates": [{"content": {"parts": [{"text": "cũ"}]}}]}) == "cũ"
    assert _find_text({"gì đó": 1}) is None


def test_parse_topics_filters_and_dedupes() -> None:
    assert _parse_topics(["llm", "LLM", "bịa"]) == [Topic.LLM]
    assert _parse_topics("không phải list") == []
    assert _parse_topics(None) == []
