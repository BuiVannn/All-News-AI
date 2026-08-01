"""arXiv qua RSS.

CỐ TÌNH chỉ dùng RSS, không dùng Query API (`export.arxiv.org/api/query`):
Query API trả HTTP 429 liên tục từ 02/2026 kể cả khi tuân thủ đúng giới hạn
1 request/3 giây, và tới giữa 06/2026 vẫn chưa có hướng giải quyết.
RSS chỉ tốn 1 request / category / ngày và đã có đủ title, abstract, tác giả.

Định dạng (theo info.arxiv.org/help/rss_specifications.html):
    description : "arXiv:2203.01250v3 Announce Type: replace-cross Abstract: ..."
    guid        : "oai:arXiv.org:2203.01250v3"

`announce_type` quan trọng: 'replace' là bản sửa của bài cũ, không phải tin
mới — để lọt vào feed sẽ toàn bài cũ. Mặc định chỉ giữ 'new' và 'cross'.

Feed rỗng vào Thứ Bảy/Chủ Nhật và ngày lễ; chính feed tự khai báo qua
<skipDays>. Rỗng là HỢP LỆ, không phải lỗi.
"""

from __future__ import annotations

import logging
import re
from datetime import date
from typing import Any, ClassVar

import feedparser
import httpx

from ai_radar import config
from ai_radar.collectors.base import Collector, parse_feed_dt, utcnow
from ai_radar.http import get_bytes
from ai_radar.models import Item, Kind, Link, Signals, arxiv_key, doi_key, make_id, title_key

logger = logging.getLogger(__name__)

FEED_URL = "https://rss.arxiv.org/rss/{category}"

# "arXiv:2203.01250v3 Announce Type: replace-cross Abstract: We consider..."
_DESCRIPTION = re.compile(
    r"arXiv:\s*(?P<arxiv_id>\S+?)\s+Announce\s+Type:\s*(?P<announce>[\w-]+)\s+Abstract:\s*(?P<abstract>.*)",
    re.IGNORECASE | re.DOTALL,
)
_GUID = re.compile(r"oai:arxiv\.org:(?P<arxiv_id>\S+)", re.IGNORECASE)
_WS = re.compile(r"\s+")


class ArxivRSSCollector(Collector):
    name: ClassVar[str] = "arxiv"
    kind: ClassVar[Kind] = Kind.PAPER

    def __init__(
        self, categories: list[str] | None = None, announce_types: list[str] | None = None
    ) -> None:
        cfg = config.section("arxiv")
        self.categories = categories or list(cfg.get("categories") or ["cs.CL"])
        self.announce_types = {
            a.lower() for a in (announce_types or cfg.get("announce_types") or ["new", "cross"])
        }

    async def fetch(self, client: httpx.AsyncClient, day: date) -> list[Item]:
        merged: dict[str, Item] = {}
        for category in self.categories:
            # Một category lỗi không được làm mất các category còn lại.
            try:
                raw = await get_bytes(client, FEED_URL.format(category=category))
            except Exception as exc:  # noqa: BLE001
                logger.warning("%s/%s: %s", self.name, category, exc)
                continue

            for entry in feedparser.parse(raw).entries:
                try:
                    item = self._parse(entry, category)
                except Exception as exc:  # noqa: BLE001
                    logger.warning("%s/%s: bỏ qua entry hỏng: %s", self.name, category, exc)
                    continue
                if item is None:
                    continue
                # Bài cross-list xuất hiện ở nhiều category — giữ bản đầu tiên.
                merged.setdefault(item.id, item)
        return list(merged.values())

    def _parse(self, entry: Any, category: str) -> Item | None:
        summary = _WS.sub(" ", str(getattr(entry, "summary", "") or "")).strip()
        guid = str(getattr(entry, "id", "") or getattr(entry, "guid", "") or "")

        match = _DESCRIPTION.match(summary)
        if match:
            arxiv_id = match.group("arxiv_id")
            announce = match.group("announce").lower()
            abstract = match.group("abstract").strip()
        else:
            # Format description đổi -> vẫn cứu được bài nhờ guid, chỉ mất
            # announce_type. Thà lấy thừa còn hơn mất trắng cả feed.
            guid_match = _GUID.search(guid)
            if not guid_match:
                raise ValueError(f"không tìm được arXiv ID trong summary lẫn guid: {guid[:60]!r}")
            logger.debug("%s: description không khớp format, dùng guid", self.name)
            arxiv_id = guid_match.group("arxiv_id")
            announce = "new"
            abstract = summary

        if announce not in self.announce_types:
            return None

        title = _WS.sub(" ", str(getattr(entry, "title", "") or "")).strip()
        if not title:
            raise ValueError(f"thiếu title cho arXiv:{arxiv_id}")

        bare_id = arxiv_key(arxiv_id).removeprefix("arxiv:")
        published = parse_feed_dt(entry) or utcnow()

        links = [
            Link(source="arxiv", url=f"https://arxiv.org/abs/{bare_id}", external_id=bare_id)
        ]
        dedup_keys = [arxiv_key(arxiv_id), title_key(title)]

        doi = str(getattr(entry, "arxiv_doi", "") or "").strip()
        if doi:
            dedup_keys.append(doi_key(doi))
            links.append(Link(source="doi", url=f"https://doi.org/{doi}", external_id=doi))

        return Item(
            id=make_id(arxiv_key(arxiv_id)),
            kind=self.kind,
            title=title,
            summary_en=abstract or None,
            links=links,
            actors=_authors(entry),
            published_at=published,
            first_seen_at=utcnow(),
            dedup_keys=dedup_keys,
            signals=Signals(),
        )


def _authors(entry: Any) -> list[str]:
    """arXiv nhét toàn bộ tác giả vào dc:creator, ngăn bằng dấu phẩy."""
    raw = str(getattr(entry, "author", "") or "")
    return [part.strip() for part in raw.split(",") if part.strip()][:20]
