"""Nạp cấu hình từ config/*.yaml.

Mọi hằng số điều chỉnh được đều nằm trong YAML chứ không hardcode: trọng số
scoring, danh sách feed, ngưỡng lọc. Code chỉ đọc.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


def _load(name: str, root: Path | None = None) -> dict[str, Any]:
    path = (root or CONFIG_DIR) / name
    if not path.exists():
        raise FileNotFoundError(f"thiếu file cấu hình: {path}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise TypeError(f"{path}: mong đợi mapping ở cấp cao nhất")
    return data


@lru_cache(maxsize=1)
def sources() -> dict[str, Any]:
    return _load("sources.yaml")


@lru_cache(maxsize=1)
def weights() -> dict[str, Any]:
    return _load("weights.yaml")


def section(name: str) -> dict[str, Any]:
    """Lấy một nhánh của sources.yaml, trả dict rỗng nếu không có."""
    value = sources().get(name)
    return value if isinstance(value, dict) else {}
