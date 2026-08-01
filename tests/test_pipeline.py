"""Điều phối pipeline — trọng tâm là cô lập lỗi giữa các nguồn."""

from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
from typing import ClassVar

import httpx

from ai_radar import store
from ai_radar.collectors.base import Collector
from ai_radar.models import Item, Kind, Signals
from ai_radar.pipeline import dedupe, run

DAY = date(2026, 7, 31)


def make_item(item_id: str, upvotes: int = 0) -> Item:
    now = datetime(2026, 7, 31, tzinfo=UTC)
    return Item(
        id=item_id,
        kind=Kind.PAPER,
        title=f"Paper {item_id}",
        published_at=now,
        first_seen_at=now,
        signals=Signals(hf_upvotes=upvotes),
    )


class FakeCollector(Collector):
    name: ClassVar[str] = "fake"
    kind: ClassVar[Kind] = Kind.PAPER

    def __init__(self, items: list[Item], name: str = "fake") -> None:
        self.items = items
        self.name = name  # type: ignore[misc]

    async def fetch(self, client: httpx.AsyncClient, day: date) -> list[Item]:
        return self.items


class BrokenCollector(Collector):
    name: ClassVar[str] = "broken"
    kind: ClassVar[Kind] = Kind.PAPER

    async def fetch(self, client: httpx.AsyncClient, day: date) -> list[Item]:
        raise RuntimeError("nguồn sập")


# --------------------------------------------------------------------------


def test_dedupe_drops_previously_seen() -> None:
    items = [make_item("a"), make_item("b")]
    fresh, dupes = dedupe(items, seen={"a"})
    assert [i.id for i in fresh] == ["b"]
    assert dupes == 1


def test_dedupe_drops_repeats_within_same_batch() -> None:
    """Cùng một paper đến từ hai nguồn trong một lượt chạy chỉ được giữ một lần."""
    items = [make_item("a"), make_item("a"), make_item("b")]
    fresh, dupes = dedupe(items, seen=set())
    assert [i.id for i in fresh] == ["a", "b"]
    assert dupes == 1


def test_broken_source_is_isolated(tmp_path: Path) -> None:
    """Nguồn sập được ghi vào manifest; nguồn còn lại vẫn cho ra dữ liệu."""
    manifest = run(
        DAY,
        root=tmp_path,
        collectors=[BrokenCollector(), FakeCollector([make_item("a")], name="good")],
    )

    assert manifest.failed_sources == ["broken"]
    assert manifest.new == 1

    broken = next(s for s in manifest.sources if s.source == "broken")
    assert broken.ok is False
    assert "nguồn sập" in (broken.error or "")

    assert [i.id for i in store.read_items(DAY, tmp_path)] == ["a"]


def test_run_writes_items_seen_and_manifest(tmp_path: Path) -> None:
    run(DAY, root=tmp_path, collectors=[FakeCollector([make_item("a"), make_item("b")])])

    assert store.items_path(DAY, tmp_path).exists()
    assert store.run_path(DAY, tmp_path).exists()
    assert store.load_seen(tmp_path) == {"a", "b"}


def test_second_run_of_same_day_is_idempotent(tmp_path: Path) -> None:
    """Cron chạy 2 lần/ngày, nên chạy lại không được nhân đôi dữ liệu."""
    collectors = [FakeCollector([make_item("a")])]

    first = run(DAY, root=tmp_path, collectors=collectors)
    second = run(DAY, root=tmp_path, collectors=collectors)

    assert first.new == 1
    assert second.new == 0
    assert store.load_seen(tmp_path) == {"a"}
    assert [i.id for i in store.read_items(DAY, tmp_path)] == ["a"]


def test_rerun_does_not_shrink_feed_to_leftovers(tmp_path: Path) -> None:
    """Hồi quy: lượt 2 từng ghi đè feed bằng phần sót lại, làm mất top item.

    Nguyên nhân: sổ `seen` loại luôn cả item của chính ngày đó khỏi danh sách
    ứng viên, nên lượt 2 chỉ còn những item hạng thấp chưa từng được chọn.
    """
    items = [make_item("top", 99), make_item("mid", 50), make_item("low", 1)]
    collectors = [FakeCollector(items)]

    run(DAY, root=tmp_path, limit=2, collectors=collectors)
    assert [i.id for i in store.read_items(DAY, tmp_path)] == ["top", "mid"]

    run(DAY, root=tmp_path, limit=2, collectors=collectors)
    assert [i.id for i in store.read_items(DAY, tmp_path)] == ["top", "mid"]


def test_rerun_promotes_item_whose_signal_grew(tmp_path: Path) -> None:
    """Upvotes tăng trong ngày thì item phải leo hạng ở lượt chạy sau."""
    early = [FakeCollector([make_item("a", 10), make_item("b", 1)])]
    run(DAY, root=tmp_path, limit=1, collectors=early)
    assert [i.id for i in store.read_items(DAY, tmp_path)] == ["a"]

    later = [FakeCollector([make_item("a", 10), make_item("b", 99)])]
    run(DAY, root=tmp_path, limit=1, collectors=later)
    assert [i.id for i in store.read_items(DAY, tmp_path)] == ["b"]


def test_item_published_yesterday_does_not_return_today(tmp_path: Path) -> None:
    """Dedup xuyên ngày: paper đã lên feed hôm qua không được xuất hiện lại."""
    collectors = [FakeCollector([make_item("a")])]
    run(DAY, root=tmp_path, collectors=collectors)

    tomorrow = date(2026, 8, 1)
    manifest = run(tomorrow, root=tmp_path, collectors=collectors)

    assert manifest.new == 0
    assert manifest.duplicates == 1
    assert store.read_items(tomorrow, tmp_path) == []


def test_limit_keeps_highest_upvotes(tmp_path: Path) -> None:
    items = [make_item("low", 1), make_item("high", 99)]

    run(DAY, root=tmp_path, limit=1, collectors=[FakeCollector(items)])
    assert [i.id for i in store.read_items(DAY, tmp_path)] == ["high"]


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    manifest = run(
        DAY, root=tmp_path, dry_run=True, collectors=[FakeCollector([make_item("a")])]
    )
    assert manifest.new == 1
    assert not store.items_path(DAY, tmp_path).exists()
    assert store.load_seen(tmp_path) == set()


def test_no_sources_succeed_is_reported(tmp_path: Path) -> None:
    manifest = run(DAY, root=tmp_path, collectors=[BrokenCollector()])
    assert manifest.new == 0
    assert not any(s.ok for s in manifest.sources)
