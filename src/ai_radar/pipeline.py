"""Điều phối một lượt chạy: fetch -> dedup -> giới hạn -> ghi.

Nguyên tắc bất di bất dịch: **mỗi nguồn độc lập hoàn toàn**. Một nguồn chết
được ghi vào manifest rồi bỏ qua, không bao giờ làm đổ cả lượt chạy.
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import httpx

from ai_radar import store
from ai_radar.collectors import REGISTRY, Collector
from ai_radar.http import build_client
from ai_radar.models import Item, RunManifest, SourceResult

logger = logging.getLogger(__name__)

DEFAULT_LIMIT = 30


async def _run_one(
    collector: Collector, client: httpx.AsyncClient, day: date
) -> tuple[SourceResult, list[Item]]:
    started = time.monotonic()
    try:
        items = await collector.fetch(client, day)
    except Exception as exc:  # noqa: BLE001 - cô lập lỗi ở ranh giới nguồn
        logger.error("nguồn %s lỗi: %s", collector.name, exc)
        return (
            SourceResult(
                source=collector.name,
                ok=False,
                error=f"{type(exc).__name__}: {exc}",
                duration_s=round(time.monotonic() - started, 2),
            ),
            [],
        )

    logger.info("nguồn %s: %d item", collector.name, len(items))
    return (
        SourceResult(
            source=collector.name,
            ok=True,
            fetched=len(items),
            duration_s=round(time.monotonic() - started, 2),
        ),
        items,
    )


async def collect(
    day: date, collectors: Sequence[Collector] | None = None
) -> tuple[list[SourceResult], list[Item]]:
    """Chạy mọi nguồn song song. Không bao giờ ném exception ra ngoài."""
    active: Sequence[Collector] = REGISTRY if collectors is None else collectors
    async with build_client() as client:
        results = await asyncio.gather(*(_run_one(c, client, day) for c in active))

    stats = [r for r, _ in results]
    items = [item for _, batch in results for item in batch]
    return stats, items


def dedupe(items: list[Item], seen: set[str]) -> tuple[list[Item], int]:
    """Bỏ item đã gặp ở lượt trước, và item trùng nhau trong cùng lượt này.

    M0 chỉ so theo `Item.id`. Gộp chéo nguồn theo `dedup_keys`
    (arXiv ID / DOI / GitHub / title mờ) sẽ vào ở M1 — xem docs/ARCHITECTURE.md §5.
    """
    fresh: list[Item] = []
    batch_ids: set[str] = set()
    duplicates = 0

    for item in items:
        if item.id in seen or item.id in batch_ids:
            duplicates += 1
            continue
        batch_ids.add(item.id)
        fresh.append(item)

    return fresh, duplicates


def run(
    day: date,
    *,
    limit: int = DEFAULT_LIMIT,
    root: Path | None = None,
    dry_run: bool = False,
    collectors: Sequence[Collector] | None = None,
) -> RunManifest:
    from ai_radar.collectors.base import utcnow

    started_at = utcnow()
    stats, raw_items = asyncio.run(collect(day, collectors))

    # Cron chạy 2 lần/ngày, nên lượt sau phải TÍNH LẠI feed của ngày đó chứ
    # không được ghi đè bằng phần sót lại. Muốn vậy phải tách hai khái niệm
    # đang lẫn trong sổ `seen`:
    #   - ID đã đăng ở NGÀY TRƯỚC  -> loại, không xét lại
    #   - ID đang nằm trong file của CHÍNH ngày này -> vẫn là ứng viên hợp lệ
    existing = {item.id: item for item in store.read_items(day, root)}
    published_earlier = store.load_seen(root) - set(existing)

    fresh, duplicates = dedupe(raw_items, published_earlier)

    # Item vừa fetch đè lên bản cũ trong file: cùng ID nhưng tín hiệu mới hơn
    # (upvotes tăng theo thời gian).
    candidates = {**existing, **{item.id: item for item in fresh}}

    # M0 xếp hạng tạm bằng upvotes. Tier-1 scoring thật (config/weights.yaml)
    # thay thế chỗ này ở M1.
    for item in candidates.values():
        item.score = float(item.signals.hf_upvotes)

    selected = sorted(candidates.values(), key=lambda i: -i.score)[:limit]

    manifest = RunManifest(
        day=day.isoformat(),
        started_at=started_at,
        finished_at=utcnow(),
        sources=stats,
        fetched=len(raw_items),
        new=sum(1 for item in selected if item.id not in existing),
        duplicates=duplicates,
    )

    if not dry_run:
        store.write_items(day, selected, root)
        store.append_seen(day, [i.id for i in selected], root)
        store.write_run(manifest, root)

    return manifest
