"""Tier-1: chấm điểm bằng luật, chạy trên toàn bộ item, chi phí bằng 0.

Mục đích là cắt từ ~600 item/ngày xuống ~30 trước khi gọi LLM ở tier-2. Tất cả
trọng số nằm trong config/weights.yaml — đây là chỗ sẽ phải chỉnh nhiều nhất,
nên không hardcode.

Tín hiệu đếm được đi qua log1p: chênh 10 -> 100 đáng kể, 10000 -> 10100 thì
không. `score_breakdown` giữ lại đóng góp của từng thành phần để soi được vì
sao một item lên hạng, thay vì phải đoán.
"""

from __future__ import annotations

import math
from datetime import datetime

from ai_radar import config
from ai_radar.collectors.base import utcnow
from ai_radar.models import Item, Topic

# Tín hiệu đếm được -> (tên trọng số, thuộc tính trong Signals)
_COUNTED = (
    ("hf_upvotes", "hf_upvotes"),
    ("hf_trending", "hf_trending_score"),
    ("hf_downloads", "hf_downloads"),
    ("hf_likes", "hf_likes"),
    ("github_stars", "github_stars"),
    ("github_stars_delta", "github_stars_delta"),
    ("hn_points", "hn_points"),
    ("reddit_score", "reddit_score"),
)

# Cờ bật/tắt -> (tên trọng số, thuộc tính trong Signals)
_FLAGS = (
    ("is_daily_paper", "is_daily_paper"),
    ("has_code", "has_code"),
    ("has_weights", "has_weights"),
)


def score_all(items: list[Item], *, now: datetime | None = None) -> None:
    """Chấm điểm tại chỗ cho toàn bộ item."""
    cfg = config.weights()
    weights: dict[str, float] = {k: float(v) for k, v in (cfg.get("weights") or {}).items()}
    kind_base: dict[str, float] = {
        str(k): float(v) for k, v in (cfg.get("kind_base") or {}).items()
    }
    known_orgs = tuple(str(o).lower() for o in (cfg.get("known_orgs") or []))
    interests = {str(t).lower() for t in (cfg.get("topics_of_interest") or [])}
    keywords: dict[str, list[str]] = {
        str(k): [str(v).lower() for v in vals]
        for k, vals in (cfg.get("topic_keywords") or {}).items()
    }
    reference = now or utcnow()

    for item in items:
        _score_one(item, weights, kind_base, known_orgs, interests, keywords, reference)


def infer_topics(item: Item, keywords: dict[str, list[str]]) -> list[Topic]:
    """Đoán chủ đề bằng từ khoá — chỗ giữ tạm cho tới khi tier-2 (LLM) gán tag."""
    haystack = f"{item.title} {item.summary_en or ''}".lower()
    found: list[Topic] = []
    for name, words in keywords.items():
        if any(word in haystack for word in words):
            try:
                found.append(Topic(name))
            except ValueError:
                continue
    return found


def _score_one(
    item: Item,
    weights: dict[str, float],
    kind_base: dict[str, float],
    known_orgs: tuple[str, ...],
    interests: set[str],
    keywords: dict[str, list[str]],
    now: datetime,
) -> None:
    breakdown: dict[str, float] = {}

    if base := kind_base.get(item.kind.value, 0.0):
        breakdown["kind_base"] = base

    for weight_name, signal_name in _COUNTED:
        raw = float(getattr(item.signals, signal_name, 0) or 0)
        if raw > 0 and (weight := weights.get(weight_name, 0.0)):
            breakdown[weight_name] = round(weight * math.log1p(raw), 3)

    for weight_name, signal_name in _FLAGS:
        if getattr(item.signals, signal_name, False) and (weight := weights.get(weight_name, 0.0)):
            breakdown[weight_name] = weight

    if _from_known_org(item, known_orgs) and (weight := weights.get("known_org", 0.0)):
        breakdown["known_org"] = weight

    if not item.topics:
        item.topics = infer_topics(item, keywords)
    matches_interest = bool(interests) and any(t.value in interests for t in item.topics)
    if matches_interest and (weight := weights.get("topic_match", 0.0)):
        breakdown["topic_match"] = weight

    age_days = max((now - item.published_at).total_seconds() / 86400.0, 0.0)
    if decay := weights.get("age_decay_per_day", 0.0):
        breakdown["age_decay"] = -round(decay * age_days, 3)

    item.score_breakdown = breakdown
    item.score = round(sum(breakdown.values()), 3)


def _from_known_org(item: Item, known_orgs: tuple[str, ...]) -> bool:
    """Khớp theo token để `meta` không ăn nhầm `metadata`, `metabolic`..."""
    if not known_orgs:
        return False
    haystack = " ".join([*item.actors, *(link.source for link in item.links)]).lower()
    tokens = set(_split(haystack))
    return any(org in tokens for org in known_orgs)


def _split(text: str) -> list[str]:
    return [chunk for chunk in "".join(c if c.isalnum() else " " for c in text).split() if chunk]


def explain(item: Item) -> str:
    """Dòng giải thích điểm số, dùng cho cờ --explain."""
    parts = sorted(item.score_breakdown.items(), key=lambda kv: -abs(kv[1]))
    detail = "  ".join(f"{name}={value:+.1f}" for name, value in parts)
    return f"{item.score:7.1f}  {item.title[:58]:<58}  {detail}"
