"""Đăng ký collector.

Thêm nguồn mới: import class rồi thêm vào REGISTRY. Pipeline tự động chạy
mọi nguồn trong đây song song.
"""

from __future__ import annotations

from ai_radar.collectors.base import Collector
from ai_radar.collectors.hf_papers import HFDailyPapersCollector

REGISTRY: list[Collector] = [
    HFDailyPapersCollector(),
]

__all__ = ["REGISTRY", "Collector", "HFDailyPapersCollector"]
