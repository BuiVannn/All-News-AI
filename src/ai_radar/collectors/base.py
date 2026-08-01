"""Hợp đồng chung cho mọi collector.

Thêm một nguồn mới = viết một class kế thừa `Collector` và đăng ký vào
`ai_radar.collectors.REGISTRY`. Không cần sửa pipeline.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import UTC, date, datetime
from typing import Any, ClassVar

import httpx

from ai_radar.models import Item, Kind


def utcnow() -> datetime:
    return datetime.now(UTC)


def parse_dt(raw: Any, fallback: datetime | None = None) -> datetime:
    """Parse ngày giờ phòng thủ — nguồn ngoài không đáng tin.

    Trả về `fallback` (mặc định: bây giờ) nếu không parse được, thay vì ném lỗi:
    một trường ngày hỏng không đáng để làm mất cả record.
    """
    if isinstance(raw, datetime):
        return raw if raw.tzinfo else raw.replace(tzinfo=UTC)
    if isinstance(raw, str) and raw.strip():
        try:
            parsed = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)
        except ValueError:
            pass
    return fallback or utcnow()


def parse_feed_dt(entry: Any) -> datetime | None:
    """Lấy ngày đăng của một entry RSS/Atom.

    Phải dùng `published_parsed` (struct_time đã chuẩn hoá) chứ KHÔNG dùng
    chuỗi `published` thô: RSS dùng RFC-822 ("Thu, 07 Aug 2025 00:00:00 GMT")
    mà `datetime.fromisoformat` không hiểu. Từng vì lỗi này mà bài từ 2025 bị
    gán ngày hôm nay và lọt qua bộ lọc cửa sổ 7 ngày — 2214 bài thay vì ~30.

    Trả về None khi không xác định được ngày. Người gọi PHẢI bỏ qua entry đó:
    trong một feed archive, entry không rõ ngày gần như chắc chắn là bài cũ,
    nên đoán "hôm nay" là sai hướng.
    """
    for field in ("published_parsed", "updated_parsed"):
        parsed = getattr(entry, field, None)
        if not parsed:
            continue
        try:
            year, month, dayofmonth, hour, minute, second = (int(v) for v in parsed[:6])
            return datetime(year, month, dayofmonth, hour, minute, second, tzinfo=UTC)
        except (TypeError, ValueError):
            continue
    return None


class Collector(ABC):
    """Một nguồn dữ liệu.

    `fetch` phải hoặc trả về list Item, hoặc ném exception. Pipeline bắt
    exception và ghi vào run manifest — một nguồn chết không làm đổ cả lượt chạy.
    """

    name: ClassVar[str]
    kind: ClassVar[Kind]

    @abstractmethod
    async def fetch(self, client: httpx.AsyncClient, day: date) -> list[Item]:
        """Lấy dữ liệu cho `day`.

        Trả về list rỗng là hợp lệ — arXiv nghỉ cuối tuần và ngày lễ.
        """
        raise NotImplementedError
