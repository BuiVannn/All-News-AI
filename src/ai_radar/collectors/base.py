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
