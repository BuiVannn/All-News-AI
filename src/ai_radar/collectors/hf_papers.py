"""Hugging Face Daily Papers.

Nguồn đã được con người curate sẵn, nên tín hiệu sạch hơn hẳn arXiv thô.
`upvotes` ở đây là tín hiệu mạnh nhất cho tier-1 scoring.

Endpoint: GET https://huggingface.co/api/daily_papers?date=YYYY-MM-DD
Không cần auth. Đã verify 2026-08-01.

Độ tin cậy của field (đo trên 50 record thật):
  id, title, summary, authors, publishedAt  100%
  githubRepo                                 64%
  githubStars                                60%
  upvotes                                    có thể bằng 0
Vì vậy mọi thứ ngoài nhóm 100% đều phải đọc bằng .get() với giá trị mặc định.
"""

from __future__ import annotations

import logging
from datetime import date
from typing import Any, ClassVar

import httpx

from ai_radar.collectors.base import Collector, parse_dt, utcnow
from ai_radar.http import get_json
from ai_radar.models import (
    Item,
    Kind,
    Link,
    Signals,
    arxiv_key,
    github_key,
    make_id,
    title_key,
)

logger = logging.getLogger(__name__)

API_URL = "https://huggingface.co/api/daily_papers"


class HFDailyPapersCollector(Collector):
    name: ClassVar[str] = "hf_papers"
    kind: ClassVar[Kind] = Kind.PAPER

    async def fetch(self, client: httpx.AsyncClient, day: date) -> list[Item]:
        payload = await get_json(
            client, API_URL, params={"date": day.isoformat(), "limit": 100}
        )
        if not isinstance(payload, list):
            raise TypeError(f"{self.name}: mong đợi list, nhận {type(payload).__name__}")

        items: list[Item] = []
        for raw in payload:
            try:
                items.append(self._parse(raw))
            except Exception as exc:  # noqa: BLE001 - một record hỏng không nên làm mất cả lượt
                logger.warning("%s: bỏ qua record hỏng: %s", self.name, exc)
        return items

    def _parse(self, raw: dict[str, Any]) -> Item:
        paper: dict[str, Any] = raw.get("paper") or {}

        arxiv_id = str(paper["id"]).strip()
        title = str(paper.get("title") or raw.get("title") or "").strip()
        if not arxiv_id or not title:
            raise ValueError("thiếu id hoặc title")

        github_repo = paper.get("githubRepo") or None
        published = parse_dt(paper.get("publishedAt") or raw.get("publishedAt"))

        links = [
            Link(
                source="hf_papers",
                url=f"https://huggingface.co/papers/{arxiv_id}",
                external_id=arxiv_id,
            ),
            Link(
                source="arxiv",
                url=f"https://arxiv.org/abs/{arxiv_id}",
                external_id=arxiv_id,
            ),
        ]
        dedup_keys = [arxiv_key(arxiv_id), title_key(title)]

        if github_repo:
            links.append(Link(source="github", url=str(github_repo)))
            dedup_keys.append(github_key(str(github_repo)))

        return Item(
            id=make_id(arxiv_key(arxiv_id)),
            kind=self.kind,
            title=title,
            summary_en=(paper.get("summary") or raw.get("summary") or "").strip() or None,
            links=links,
            actors=[
                str(a["name"]).strip()
                for a in (paper.get("authors") or [])
                if isinstance(a, dict) and a.get("name")
            ],
            published_at=published,
            first_seen_at=utcnow(),
            dedup_keys=dedup_keys,
            signals=Signals(
                hf_upvotes=int(paper.get("upvotes") or 0),
                is_daily_paper=True,
                github_stars=int(paper.get("githubStars") or 0),
                num_comments=int(raw.get("numComments") or 0),
                has_code=bool(github_repo),
            ),
        )
