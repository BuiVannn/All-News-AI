"""Tin ra mắt từ blog chính thức của các lab.

Hai điều học được khi dò feed thật (2026-08-01):

1. Feed trả TOÀN BỘ archive, không phải bài gần đây: OpenAI 1105 bài,
   Hugging Face 834. Bắt buộc lọc theo cửa sổ thời gian, nếu không lượt chạy
   đầu tiên sẽ nuốt trọn nhiều năm lịch sử.

2. Feed chết âm thầm: RSS của Qwen vẫn trả HTTP 200 và 44 bài, nhưng bài mới
   nhất đã 312 ngày tuổi. Không có lỗi nào để bắt. Vì vậy collector tự đo tuổi
   bài mới nhất và ghi cảnh báo — đây là failure mode khó phát hiện nhất.

Anthropic, Meta AI, Mistral, DeepSeek không publish RSS ở path thông thường
(đã dò 2026-08-01) nên vắng mặt; sẽ phủ gián tiếp qua HN/Reddit ở M4.
"""

from __future__ import annotations

import logging
import re
from datetime import date, datetime, timedelta
from typing import Any, ClassVar

import feedparser
import httpx

from ai_radar import config
from ai_radar.collectors.base import Collector, parse_feed_dt, utcnow
from ai_radar.http import get_bytes
from ai_radar.models import Item, Kind, Link, Signals, make_id, title_key, url_key

logger = logging.getLogger(__name__)

_TAGS = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")
SUMMARY_CHARS = 600


class BlogsRSSCollector(Collector):
    name: ClassVar[str] = "blogs"
    kind: ClassVar[Kind] = Kind.RELEASE

    def __init__(
        self,
        feeds: list[dict[str, str]] | None = None,
        window_days: int | None = None,
        stale_after_days: int | None = None,
    ) -> None:
        cfg = config.section("blogs")
        self.feeds = feeds if feeds is not None else list(cfg.get("feeds") or [])
        self.window_days = (
            window_days if window_days is not None else int(cfg.get("window_days", 7))
        )
        self.stale_after_days = (
            stale_after_days
            if stale_after_days is not None
            else int(cfg.get("stale_after_days", 120))
        )

    async def fetch(self, client: httpx.AsyncClient, day: date) -> list[Item]:
        now = utcnow()
        cutoff = now - timedelta(days=self.window_days)
        items: list[Item] = []

        for feed in self.feeds:
            source, url = str(feed.get("name") or "blog"), str(feed.get("url") or "")
            if not url:
                continue
            # Một blog lỗi không được làm mất các blog còn lại.
            try:
                raw = await get_bytes(client, url)
            except Exception as exc:  # noqa: BLE001
                logger.warning("%s/%s: %s", self.name, source, exc)
                continue

            entries = feedparser.parse(raw).entries
            newest: datetime | None = None

            undated = 0
            for entry in entries:
                published = parse_feed_dt(entry)
                if published is None:
                    # Không đoán "hôm nay": trong feed archive, entry không rõ
                    # ngày gần như chắc chắn là bài cũ.
                    undated += 1
                    continue
                if newest is None or published > newest:
                    newest = published
                if published < cutoff:
                    continue
                try:
                    items.append(self._parse(entry, source, published))
                except Exception as exc:  # noqa: BLE001
                    logger.warning("%s/%s: bỏ qua entry hỏng: %s", self.name, source, exc)

            if undated:
                logger.warning(
                    "%s/%s: %d entry không xác định được ngày đăng, đã bỏ qua",
                    self.name, source, undated,
                )
            self._warn_if_stale(source, newest, now, len(entries))

        return items

    def _warn_if_stale(
        self, source: str, newest: datetime | None, now: datetime, total: int
    ) -> None:
        if newest is None:
            logger.warning("%s/%s: feed không có bài nào (%d entry)", self.name, source, total)
            return
        age = (now - newest).days
        if age > self.stale_after_days:
            logger.warning(
                "%s/%s: feed có vẻ đã chết — bài mới nhất %d ngày tuổi", self.name, source, age
            )

    def _parse(self, entry: Any, source: str, published: datetime) -> Item:
        title = _clean(str(getattr(entry, "title", "") or ""))
        url = str(getattr(entry, "link", "") or "").strip()
        if not title or not url:
            raise ValueError(f"thiếu title hoặc link ({title[:40]!r})")

        summary = _clean(str(getattr(entry, "summary", "") or ""))

        return Item(
            id=make_id(url_key(url)),
            kind=self.kind,
            title=title,
            summary_en=summary[:SUMMARY_CHARS] or None,
            links=[Link(source=source, url=url)],
            actors=[source],
            published_at=published,
            first_seen_at=utcnow(),
            dedup_keys=[url_key(url), title_key(title)],
            signals=Signals(),
        )


def _clean(text: str) -> str:
    """Blog RSS thường nhét HTML vào summary — bỏ thẻ, gộp khoảng trắng."""
    return _WS.sub(" ", _TAGS.sub(" ", text)).strip()
