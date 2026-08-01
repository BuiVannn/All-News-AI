"""Gộp item trùng giữa các nguồn — phần tạo ra giá trị của dự án.

Cùng một sự kiện xuất hiện ở nhiều nơi: paper trên arXiv, model trên HF, repo
trên GitHub, bài blog của lab. Công cụ khác hiển thị 5 dòng; ở đây gộp thành
MỘT mục có 5 đường dẫn.

Thứ tự khoá (docs/ARCHITECTURE.md §5), khớp khoá nào cũng gộp:
    1. arXiv ID đã bỏ version   arxiv:2508.01234
    2. DOI                      doi:10.1234/abc
    3. GitHub repo              github:owner/repo
    4. HF repo                  hf:org/model
    5. URL đã chuẩn hoá         url:example.com/post
    6. Tiêu đề, chỉ trong cửa sổ ±N ngày và chỉ giữa item cùng `kind`

Tầng 6 phải chặn theo thời gian và theo kind, nếu không sẽ vừa chậm O(n²)
vừa gộp nhầm các bài trùng tên qua nhiều năm.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from difflib import SequenceMatcher
from typing import TypeVar

from ai_radar import config
from ai_radar.models import Item

logger = logging.getLogger(__name__)

TITLE_PREFIX = "title:"
# Trần kích thước block khớp mờ, chặn trường hợp bệnh lý O(n²).
MAX_BLOCK = 200
T = TypeVar("T")


class _Union:
    """Union-find: gom các item nối với nhau qua bất kỳ khoá chung nào."""

    def __init__(self, size: int) -> None:
        self.parent = list(range(size))

    def find(self, node: int) -> int:
        while self.parent[node] != node:
            self.parent[node] = self.parent[self.parent[node]]
            node = self.parent[node]
        return node

    def union(self, a: int, b: int) -> None:
        root_a, root_b = self.find(a), self.find(b)
        if root_a != root_b:
            self.parent[max(root_a, root_b)] = min(root_a, root_b)


def merge(
    items: list[Item],
    *,
    title_window_days: int | None = None,
    title_similarity: float | None = None,
) -> tuple[list[Item], int]:
    """Gộp item trùng. Trả về (danh sách đã gộp, số item bị gộp đi)."""
    if len(items) < 2:
        return list(items), 0

    cfg = config.section("dedup")
    window = title_window_days if title_window_days is not None else int(
        cfg.get("title_window_days", 7)
    )
    threshold = title_similarity if title_similarity is not None else float(
        cfg.get("title_similarity", 0.92)
    )

    union = _Union(len(items))

    # Tầng 1-5: khoá mạnh, khớp chính xác là gộp ngay.
    by_key: dict[str, int] = {}
    for index, item in enumerate(items):
        for key in item.dedup_keys:
            if key.startswith(TITLE_PREFIX):
                continue
            if key in by_key:
                union.union(by_key[key], index)
            else:
                by_key[key] = index

    _link_by_title(items, union, window, threshold)

    groups: dict[int, list[Item]] = defaultdict(list)
    for index, item in enumerate(items):
        groups[union.find(index)].append(item)

    merged = [_combine(group) for group in groups.values()]
    return merged, len(items) - len(merged)


def _link_by_title(items: list[Item], union: _Union, window: int, threshold: float) -> None:
    """Tầng 6: so tiêu đề, chỉ trong cùng `kind` và cùng cửa sổ thời gian."""
    buckets: dict[tuple[str, str], list[int]] = defaultdict(list)
    for index, item in enumerate(items):
        for key in item.dedup_keys:
            if key.startswith(TITLE_PREFIX):
                buckets[(item.kind.value, key)].append(index)

    # Khớp token-set chính xác (đã bỏ dấu câu, không quan tâm thứ tự từ).
    for indexes in buckets.values():
        for other in indexes[1:]:
            if _within_window(items[indexes[0]], items[other], window):
                union.union(indexes[0], other)

    # Khớp mờ cho tiêu đề lệch nhẹ, chặn lại để khỏi O(n²) trên toàn bộ item.
    #
    # Khoá chặn là 3 token DÀI NHẤT, không phải 3 token đầu: `title_key` sắp xếp
    # token theo alphabet, nên chỉ cần thêm một hư từ ("in" -> "for") là 3 token
    # đầu đổi hẳn và hai tiêu đề gần như giống nhau rơi vào hai block khác nhau.
    # Token dài mang tính phân biệt cao và ổn định trước thay đổi kiểu đó.
    blocks: dict[tuple[str, str], list[tuple[int, str]]] = defaultdict(list)
    for (kind, key), indexes in buckets.items():
        tokens = key.removeprefix(TITLE_PREFIX).split()
        for token in sorted(set(tokens), key=len, reverse=True)[:3]:
            blocks[(kind, token)].append((indexes[0], key))

    for (kind, token), candidates in blocks.items():
        if len(candidates) > MAX_BLOCK:
            # Token quá phổ biến ("model", "learning") -> block khổng lồ. So hết
            # sẽ rất chậm mà gần như không gộp thêm được gì, vì tiêu đề thật sự
            # trùng nhau đã chia sẻ những token hiếm hơn.
            logger.debug("bỏ qua block quá lớn %s/%s (%d mục)", kind, token, len(candidates))
            continue
        for i in range(len(candidates)):
            for j in range(i + 1, len(candidates)):
                left_index, left_key = candidates[i]
                right_index, right_key = candidates[j]
                if union.find(left_index) == union.find(right_index):
                    continue
                if not _within_window(items[left_index], items[right_index], window):
                    continue
                if SequenceMatcher(None, left_key, right_key).ratio() >= threshold:
                    logger.debug("gộp mờ theo tiêu đề: %r ~ %r", left_key, right_key)
                    union.union(left_index, right_index)


def _within_window(left: Item, right: Item, window_days: int) -> bool:
    return abs((left.published_at - right.published_at).days) <= window_days


def _combine(group: list[Item]) -> Item:
    """Gộp một nhóm thành một item.

    Bản gốc là item có `published_at` sớm nhất — thường là bài arXiv gốc chứ
    không phải bài blog viết lại. Link và tín hiệu thì hợp nhất từ cả nhóm.
    """
    if len(group) == 1:
        return group[0]

    ordered = sorted(group, key=lambda i: i.published_at)
    primary = ordered[0].model_copy(deep=True)

    seen_urls = {link.url for link in primary.links}
    for other in ordered[1:]:
        for link in other.links:
            if link.url not in seen_urls:
                seen_urls.add(link.url)
                primary.links.append(link)

        primary.actors = _unique(primary.actors + other.actors)
        primary.topics = _unique(primary.topics + other.topics)
        primary.dedup_keys = _unique(primary.dedup_keys + other.dedup_keys)

        if primary.summary_en is None and other.summary_en:
            primary.summary_en = other.summary_en
        if other.first_seen_at < primary.first_seen_at:
            primary.first_seen_at = other.first_seen_at

        _merge_signals(primary, other)

    return primary


def _merge_signals(primary: Item, other: Item) -> None:
    """Lấy giá trị lớn nhất mỗi tín hiệu — nguồn nào biết nhiều hơn thì thắng."""
    for field in type(primary.signals).model_fields:
        mine = getattr(primary.signals, field)
        theirs = getattr(other.signals, field)
        if isinstance(mine, bool):
            setattr(primary.signals, field, mine or theirs)
        else:
            setattr(primary.signals, field, max(mine, theirs))


def _unique(values: list[T]) -> list[T]:
    return list(dict.fromkeys(values))
