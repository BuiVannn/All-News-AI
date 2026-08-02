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

from ai_radar import config, dedup, scoring, store
from ai_radar.collectors import Collector, default_registry
from ai_radar.enrich import Enricher, EnrichResult, build_enricher
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
    active: Sequence[Collector] = default_registry() if collectors is None else collectors
    async with build_client() as client:
        results = await asyncio.gather(*(_run_one(c, client, day) for c in active))

    stats = [r for r, _ in results]
    items = [item for _, batch in results for item in batch]
    return stats, items


def dedupe(items: list[Item], seen: set[str]) -> tuple[list[Item], int]:
    """Lọc theo `Item.id`: bỏ item đã đăng ngày trước và trùng trong cùng lượt.

    Đây chỉ là bước lọc rẻ tiền trước. Gộp chéo nguồn thật sự (arXiv ID / DOI /
    GitHub / HF / URL / tiêu đề) nằm ở `dedup.merge` — xem docs/ARCHITECTURE.md §5.
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


async def _enrich(items: list[Item], enricher: Enricher | None) -> EnrichResult:
    """Sinh tóm tắt tiếng Việt. Không bao giờ được làm hỏng lượt chạy."""
    active = enricher or build_enricher()
    async with build_client() as client:
        try:
            return await active.enrich(client, items)
        except Exception as exc:  # noqa: BLE001 - nội dung là thứ có thì tốt
            logger.error("bước enrich lỗi: %s", exc)
            return EnrichResult(
                provider=active.name, requested=len(items), failed=len(items)
            )


def select(candidates: list[Item], limit: int) -> list[Item]:
    """Chọn `limit` item, đảm bảo suất tối thiểu cho từng loại.

    Xếp thuần theo điểm thì model chiếm hết: model có ba tín hiệu đếm được
    (trending/downloads/likes), paper chỉ có upvotes, còn tin blog thì không có
    tín hiệu nào. Một lượt chạy thật cho ra 26/30 mục là model.

    Hạn ngạch lấp trước, phần ghế còn lại xếp thuần theo điểm.
    """
    ranked = sorted(candidates, key=lambda i: -i.score)
    quotas: dict[str, int] = {
        str(k): int(v) for k, v in (config.section("feed").get("quotas") or {}).items()
    }

    # Cấp phát XOAY VÒNG, không duyệt tuần tự từng loại: tổng hạn ngạch có thể
    # lớn hơn `limit` (25 > 10 chẳng hạn), và khi đó loại đứng đầu sẽ nuốt trọn
    # số ghế, đúng cái mà hạn ngạch sinh ra để ngăn.
    pools: dict[str, list[Item]] = {kind: [] for kind in quotas}
    for item in ranked:
        if item.kind.value in pools:
            pools[item.kind.value].append(item)

    chosen: list[Item] = []
    taken: set[str] = set()
    remaining = dict(quotas)

    while len(chosen) < limit:
        progressed = False
        for kind in quotas:
            if len(chosen) >= limit or remaining[kind] <= 0 or not pools[kind]:
                continue
            item = pools[kind].pop(0)
            chosen.append(item)
            taken.add(item.id)
            remaining[kind] -= 1
            progressed = True
        if not progressed:
            break

    # Ghế còn trống (loại nào đó không đủ item) thì nhường cho điểm cao nhất.
    for item in ranked:
        if len(chosen) >= limit:
            break
        if item.id not in taken:
            chosen.append(item)
            taken.add(item.id)

    return sorted(chosen, key=lambda i: -i.score)


def run(
    day: date,
    *,
    limit: int = DEFAULT_LIMIT,
    root: Path | None = None,
    dry_run: bool = False,
    collectors: Sequence[Collector] | None = None,
    enricher: Enricher | None = None,
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
    candidates = list({**existing, **{item.id: item for item in fresh}}.values())

    # Gộp chéo nguồn: cùng một sự kiện ở arXiv + HF + GitHub + blog thành MỘT
    # item nhiều link. Chạy sau khi hợp nhất để bắt được cả trùng giữa các nguồn
    # lẫn trùng với những gì đã ghi hôm nay.
    candidates, merged_away = dedup.merge(candidates)

    scoring.score_all(candidates)
    selected = select(candidates, limit)

    # Enrich SAU khi chọn: chỉ ~30 item được gọi LLM thay vì cả trăm ứng viên.
    # Đây chính là lý do tier-1 tồn tại.
    enrichment = asyncio.run(_enrich(selected, enricher))

    manifest = RunManifest(
        day=day.isoformat(),
        started_at=started_at,
        finished_at=utcnow(),
        sources=stats,
        fetched=len(raw_items),
        new=sum(1 for item in selected if item.id not in existing),
        duplicates=duplicates + merged_away,
        merged=merged_away,
        enrichment=enrichment,
    )

    if not dry_run:
        store.write_items(day, selected, root)
        store.append_seen(day, [i.id for i in selected], root)
        store.write_run(manifest, root)

    return manifest
