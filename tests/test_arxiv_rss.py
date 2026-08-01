"""arXiv RSS.

Fixture dựng theo spec chứ không phải bản chụp thật (feed rỗng cuối tuần), nên
có thêm `test_live_feed_matches_parser` đánh dấu `live` để bắt sai lệch giữa
spec và thực tế: `pytest -m live`.
"""

from __future__ import annotations

from datetime import date
from pathlib import Path

import httpx
import pytest
import respx

from ai_radar.collectors.arxiv_rss import FEED_URL, ArxivRSSCollector
from ai_radar.http import build_client
from ai_radar.models import Item, Kind

FIXTURES = Path(__file__).parent / "fixtures"
DAY = date(2026, 7, 29)
CATEGORY = "cs.CL"
URL = FEED_URL.format(category=CATEGORY)


async def _fetch(xml: bytes, announce_types: list[str] | None = None) -> list[Item]:
    collector = ArxivRSSCollector(categories=[CATEGORY], announce_types=announce_types)
    with respx.mock:
        respx.get(URL).mock(return_value=httpx.Response(200, content=xml))
        async with build_client() as client:
            return await collector.fetch(client, DAY)


@pytest.fixture
def feed() -> bytes:
    return (FIXTURES / "arxiv_cs_cl.xml").read_bytes()


async def test_parses_new_and_cross_only(feed: bytes) -> None:
    """'replace' là bản sửa của bài cũ, không phải tin mới — phải loại."""
    items = await _fetch(feed)
    titles = {i.title for i in items}

    assert "Sparse Routing Improves Long-Context Retrieval in Language Models" in titles
    assert "Cross-Modal Grounding for Embodied Agents" in titles
    assert "An Older Paper Being Revised Again" not in titles


async def test_replace_can_be_opted_in(feed: bytes) -> None:
    items = await _fetch(feed, announce_types=["new", "cross", "replace-cross"])
    assert any("Older Paper" in i.title for i in items)


async def test_strips_arxiv_version_from_id_and_links(feed: bytes) -> None:
    """v1/v2 của cùng bài phải cho cùng ID, nếu không sẽ thành hai mục."""
    item = next(i for i in await _fetch(feed) if "Cross-Modal" in i.title)
    link = next(link for link in item.links if link.source == "arxiv")

    assert link.url == "https://arxiv.org/abs/2607.22222"
    assert "arxiv:2607.22222" in item.dedup_keys
    assert "arxiv:2607.22222v2" not in item.dedup_keys


async def test_extracts_abstract_authors_and_doi(feed: bytes) -> None:
    items = await _fetch(feed)
    sparse = next(i for i in items if "Sparse Routing" in i.title)
    assert (sparse.summary_en or "").startswith("We study how sparse routing")
    assert sparse.actors == ["Mai Tran", "Kenji Watanabe", "Priya Raman"]
    assert sparse.kind is Kind.PAPER

    cross = next(i for i in items if "Cross-Modal" in i.title)
    assert "doi:10.1234/example.2607.22222" in cross.dedup_keys


async def test_parses_rfc822_pubdate(feed: bytes) -> None:
    """RSS dùng RFC-822, không phải ISO — từng gây bug lọt bài cũ vào cửa sổ."""
    item = next(i for i in await _fetch(feed) if "Sparse Routing" in i.title)
    assert item.published_at.year == 2026
    assert item.published_at.month == 7
    assert item.published_at.day == 29


async def test_falls_back_to_guid_when_description_format_changes(feed: bytes) -> None:
    """Thà lấy thừa một bài còn hơn mất trắng cả feed khi arXiv đổi format."""
    item = next(i for i in await _fetch(feed) if "Description Format Changed" in i.title)
    assert "arxiv:2607.33333" in item.dedup_keys


async def test_entry_without_title_is_skipped(feed: bytes) -> None:
    assert all("2607.44444" not in str(i.dedup_keys) for i in await _fetch(feed))


async def test_weekend_empty_feed_is_valid_not_an_error() -> None:
    """arXiv nghỉ T7/CN (feed tự khai <skipDays>). Rỗng là hợp lệ."""
    xml = (FIXTURES / "arxiv_weekend_empty.xml").read_bytes()
    assert await _fetch(xml) == []


async def test_one_dead_category_does_not_lose_the_others(feed: bytes) -> None:
    collector = ArxivRSSCollector(categories=["cs.CL", "cs.CV"])
    with respx.mock:
        respx.get(FEED_URL.format(category="cs.CL")).mock(
            return_value=httpx.Response(200, content=feed)
        )
        respx.get(FEED_URL.format(category="cs.CV")).mock(return_value=httpx.Response(503))
        async with build_client() as client:
            items = await collector.fetch(client, DAY)
    assert len(items) == 3


async def test_cross_listed_paper_is_not_duplicated(feed: bytes) -> None:
    """Bài cross-list xuất hiện ở nhiều category — chỉ được tính một lần."""
    collector = ArxivRSSCollector(categories=["cs.CL", "cs.LG"])
    with respx.mock:
        for category in ("cs.CL", "cs.LG"):
            respx.get(FEED_URL.format(category=category)).mock(
                return_value=httpx.Response(200, content=feed)
            )
        async with build_client() as client:
            items = await collector.fetch(client, DAY)

    assert len({i.id for i in items}) == len(items) == 3


@pytest.mark.live
async def test_live_feed_matches_parser() -> None:
    """Chạm feed arXiv thật. Bỏ qua khi feed rỗng (cuối tuần / ngày lễ).

    Fixture ở trên dựng theo tài liệu; test này mới là thứ chứng minh tài liệu
    khớp thực tế. Chạy bằng: pytest -m live
    """
    collector = ArxivRSSCollector(categories=["cs.CL"])
    async with build_client() as client:
        items = await collector.fetch(client, date.today())

    if not items:
        pytest.skip("feed arXiv rỗng (cuối tuần hoặc ngày lễ)")

    assert all(i.title and i.published_at for i in items)
    assert all(any(k.startswith("arxiv:") for k in i.dedup_keys) for i in items)
    # Nếu điều này fail, format `description` đã đổi và parser đang rơi về guid.
    assert sum(1 for i in items if i.summary_en) / len(items) > 0.9
