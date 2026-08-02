"""Chọn enricher theo cấu hình + biến môi trường.

Không có API key -> NullEnricher. Pipeline chạy y hệt, chỉ thiếu tóm tắt.
"""

from __future__ import annotations

import logging

from ai_radar import config
from ai_radar.enrich.base import Enricher, EnrichResult, NullEnricher
from ai_radar.enrich.gemini import GeminiEnricher
from ai_radar.enrich.gemini import from_env as _gemini_from_env

logger = logging.getLogger(__name__)


def build_enricher() -> Enricher:
    cfg = config.section("enrich")
    provider = str(cfg.get("provider") or "none").strip().lower()

    if provider in ("", "none", "null"):
        return NullEnricher()

    if provider == "gemini":
        enricher = _gemini_from_env(
            model=str(cfg.get("model") or "gemini-2.5-flash-lite"),
            concurrency=int(cfg.get("concurrency") or 4),
        )
        if enricher is None:
            logger.warning(
                "enrich.provider=gemini nhưng chưa có GEMINI_API_KEY — bỏ qua bước enrich"
            )
            return NullEnricher()
        return enricher

    logger.warning("enrich.provider=%r không nhận diện được — bỏ qua bước enrich", provider)
    return NullEnricher()


__all__ = [
    "EnrichResult",
    "Enricher",
    "GeminiEnricher",
    "NullEnricher",
    "build_enricher",
]
