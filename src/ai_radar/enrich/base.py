"""Tầng enrich (tier-2): sinh tóm tắt tiếng Việt.

Cố tình tách khỏi nhà cung cấp cụ thể. Đổi Gemini sang Groq hay Claude chỉ là
sửa một dòng trong config, không đụng vào pipeline.

`NullEnricher` là mặc định và không cần API key nào — feed vẫn chạy, chỉ là
`summary_vi` để trống. Nhờ vậy web lên sóng được trước khi có key.
"""

from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import ClassVar

import httpx

from ai_radar.models import EnrichResult, Item

logger = logging.getLogger(__name__)


class Enricher(ABC):
    """Sinh nội dung tiếng Việt cho item.

    Enrich KHÔNG BAO GIỜ được làm hỏng lượt chạy: nhà cung cấp lỗi thì item vẫn
    lên feed, chỉ thiếu tóm tắt. Nội dung là thứ có thì tốt, không phải bắt buộc.
    """

    name: ClassVar[str]

    @abstractmethod
    async def enrich(self, client: httpx.AsyncClient, items: list[Item]) -> EnrichResult:
        raise NotImplementedError

    @staticmethod
    def pending(items: list[Item]) -> list[Item]:
        """Chỉ enrich item chưa có tóm tắt — chạy lại không tốn thêm quota."""
        return [item for item in items if not item.summary_vi]


class NullEnricher(Enricher):
    """Không gọi mạng. Dùng khi chưa cấu hình API key."""

    name: ClassVar[str] = "none"

    async def enrich(self, client: httpx.AsyncClient, items: list[Item]) -> EnrichResult:
        pending = self.pending(items)
        if pending:
            logger.info(
                "chưa cấu hình nhà cung cấp enrich — %d item sẽ hiển thị không có "
                "tóm tắt tiếng Việt",
                len(pending),
            )
        return EnrichResult(
            provider=self.name, requested=len(pending), skipped=len(pending)
        )


__all__ = ["EnrichResult", "Enricher", "NullEnricher"]
