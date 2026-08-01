"""Blog RSS của các lab.

Fixture là bản chụp thật từ feed OpenAI, giữ 3 bài mới (07/2026) và 2 bài cũ
(03/2025) để khoá lại bộ lọc cửa sổ thời gian.
"""

from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import httpx
import pytest
import respx

from ai_radar.collectors.blogs_rss import BlogsRSSCollector
from ai_radar.http import build_client
from ai_radar.models import Item, Kind

FIXTURES = Path(__file__).parent / "fixtures"
URL = "https://example.test/feed.xml"
FEEDS = [{"name": "openai", "url": URL}]

# Fixture có bài mới nhất ngày 2026-08-01; neo "hôm nay" vào đó cho ổn định.
DAY = date(2026, 8, 1)


@pytest.fixture
def feed() -> bytes:
    return (FIXTURES / "blog_openai.xml").read_bytes()


async def _fetch(xml: bytes, **kwargs: int) -> list[Item]:
    collector = BlogsRSSCollector(feeds=FEEDS, **kwargs)
    with respx.mock:
        respx.get(URL).mock(return_value=httpx.Response(200, content=xml))
        async with build_client() as client:
            return await collector.fetch(client, DAY)


async def test_window_filter_rejects_the_archive(feed: bytes) -> None:
    """Hồi quy: feed trả TOÀN BỘ archive, không phải bài gần đây.

    Bug gốc: `published` của RSS là RFC-822 ("Thu, 07 Aug 2025 00:00:00 GMT"),
    `datetime.fromisoformat` không parse được nên rơi vào fallback = hiện tại,
    khiến mọi bài đều lọt cửa sổ. Kết quả: 2214 item thay vì ~30.
    """
    items = await _fetch(feed, window_days=3650)
    assert len(items) == 5, "cửa sổ 10 năm phải lấy hết fixture"

    recent = await _fetch(feed, window_days=7)
    assert len(recent) == 3
    assert all(i.published_at.year == 2026 for i in recent)


async def test_rfc822_dates_are_parsed_not_defaulted_to_now(feed: bytes) -> None:
    items = await _fetch(feed, window_days=3650)
    old = [i for i in items if i.published_at.year == 2025]

    assert len(old) == 2, "bài 03/2025 phải giữ đúng năm, không bị gán ngày hôm nay"
    assert {i.published_at.month for i in old} == {3}


async def test_builds_item_with_link_and_dedup_keys(feed: bytes) -> None:
    item = (await _fetch(feed, window_days=7))[0]

    assert item.kind is Kind.RELEASE
    assert item.actors == ["openai"]
    assert item.links[0].source == "openai"
    assert item.links[0].url.startswith("https://")
    assert any(k.startswith("url:") for k in item.dedup_keys)
    assert any(k.startswith("title:") for k in item.dedup_keys)


async def test_summary_html_is_stripped(feed: bytes) -> None:
    for item in await _fetch(feed, window_days=3650):
        assert "<" not in (item.summary_en or "")


def test_stale_feed_is_reported(caplog: pytest.LogCaptureFixture) -> None:
    """Feed chết âm thầm (Qwen: HTTP 200, 44 bài, bài mới nhất 312 ngày tuổi).

    Không có lỗi nào để bắt, nên phải tự đo tuổi bài mới nhất. Gọi thẳng
    `_warn_if_stale` với `now` tường minh để test không phụ thuộc ngày chạy.
    """
    collector = BlogsRSSCollector(feeds=FEEDS, stale_after_days=120)
    now = datetime(2026, 8, 1, tzinfo=UTC)

    with caplog.at_level(logging.WARNING):
        collector._warn_if_stale("qwen", now - timedelta(days=312), now, 44)
    assert "đã chết" in caplog.text
    assert "312" in caplog.text


def test_healthy_feed_is_not_reported_stale(caplog: pytest.LogCaptureFixture) -> None:
    collector = BlogsRSSCollector(feeds=FEEDS, stale_after_days=120)
    now = datetime(2026, 8, 1, tzinfo=UTC)

    with caplog.at_level(logging.WARNING):
        collector._warn_if_stale("openai", now - timedelta(days=2), now, 100)
    assert "đã chết" not in caplog.text


def test_empty_feed_is_reported(caplog: pytest.LogCaptureFixture) -> None:
    collector = BlogsRSSCollector(feeds=FEEDS)
    with caplog.at_level(logging.WARNING):
        collector._warn_if_stale("dead", None, datetime(2026, 8, 1, tzinfo=UTC), 0)
    assert "không có bài nào" in caplog.text


async def test_one_dead_feed_does_not_lose_the_others(feed: bytes) -> None:
    collector = BlogsRSSCollector(
        feeds=[{"name": "dead", "url": "https://dead.test/f.xml"}, *FEEDS],
        window_days=7,
    )
    with respx.mock:
        respx.get("https://dead.test/f.xml").mock(return_value=httpx.Response(503))
        respx.get(URL).mock(return_value=httpx.Response(200, content=feed))
        async with build_client() as client:
            items = await collector.fetch(client, DAY)
    assert len(items) == 3


async def test_undated_entries_are_skipped_not_dated_now() -> None:
    """Trong feed archive, entry không rõ ngày gần như chắc chắn là bài cũ."""
    xml = b"""<?xml version="1.0"?><rss version="2.0"><channel>
      <title>t</title><link>https://x.test</link><description>d</description>
      <item><title>Khong co ngay</title><link>https://x.test/a</link>
        <description>abc</description></item>
    </channel></rss>"""
    assert await _fetch(xml, window_days=7) == []
