"""Đăng ký collector.

Thêm nguồn mới: import class rồi thêm vào REGISTRY. Pipeline tự động chạy
mọi nguồn trong đây song song.
"""

from __future__ import annotations

from ai_radar.collectors.arxiv_rss import ArxivRSSCollector
from ai_radar.collectors.base import Collector
from ai_radar.collectors.blogs_rss import BlogsRSSCollector
from ai_radar.collectors.hf_models import HFModelsCollector
from ai_radar.collectors.hf_papers import HFDailyPapersCollector


def default_registry() -> list[Collector]:
    """Dựng mới mỗi lần gọi để collector đọc lại config, tiện cho test."""
    return [
        HFDailyPapersCollector(),
        ArxivRSSCollector(),
        HFModelsCollector(),
        BlogsRSSCollector(),
    ]


REGISTRY: list[Collector] = default_registry()

__all__ = [
    "REGISTRY",
    "ArxivRSSCollector",
    "BlogsRSSCollector",
    "Collector",
    "HFDailyPapersCollector",
    "HFModelsCollector",
    "default_registry",
]
