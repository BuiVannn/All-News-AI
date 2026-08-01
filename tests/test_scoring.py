"""Tier-1 scoring.

Điểm số phải giải thích được: `score_breakdown` giữ đóng góp của từng thành
phần để soi được vì sao một item lên hạng, thay vì phải đoán.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from ai_radar.models import Item, Kind, Link, Signals
from ai_radar.scoring import explain, score_all

NOW = datetime(2026, 7, 31, 12, tzinfo=UTC)


def make(
    *,
    title: str = "Một paper nào đó",
    summary: str | None = None,
    kind: Kind = Kind.PAPER,
    signals: Signals | None = None,
    actors: list[str] | None = None,
    age_days: float = 0.0,
) -> Item:
    return Item(
        id="x",
        kind=kind,
        title=title,
        summary_en=summary,
        links=[Link(source="arxiv", url="https://arxiv.org/abs/1")],
        actors=actors or [],
        published_at=NOW - timedelta(days=age_days),
        first_seen_at=NOW,
        signals=signals or Signals(),
    )


def score(item: Item) -> float:
    score_all([item], now=NOW)
    return item.score


# --------------------------------------------------------------------------


def test_breakdown_sums_to_score() -> None:
    item = make(signals=Signals(hf_upvotes=100, is_daily_paper=True, has_code=True))
    score_all([item], now=NOW)
    assert item.score == pytest.approx(sum(item.score_breakdown.values()), abs=0.01)


def test_more_upvotes_scores_higher() -> None:
    low = make(signals=Signals(hf_upvotes=5))
    high = make(signals=Signals(hf_upvotes=500))
    assert score(high) > score(low)


def test_counted_signals_use_log_scale() -> None:
    """Chênh 10 -> 100 phải đáng kể hơn hẳn 1000 -> 1090."""
    small_jump = score(make(signals=Signals(hf_upvotes=100))) - score(
        make(signals=Signals(hf_upvotes=10))
    )
    big_jump = score(make(signals=Signals(hf_upvotes=1090))) - score(
        make(signals=Signals(hf_upvotes=1000))
    )
    assert small_jump > big_jump


def test_older_items_decay() -> None:
    assert score(make(age_days=0)) > score(make(age_days=5))


def test_daily_paper_flag_adds_a_bonus() -> None:
    assert score(make(signals=Signals(is_daily_paper=True))) > score(make())


def test_code_and_weights_add_bonuses() -> None:
    assert score(make(signals=Signals(has_code=True))) > score(make())
    assert score(make(signals=Signals(has_weights=True))) > score(make())


def test_known_org_adds_a_bonus() -> None:
    item = make(actors=["deepseek"])
    score_all([item], now=NOW)
    assert "known_org" in item.score_breakdown


def test_known_org_matches_whole_tokens_only() -> None:
    """`meta` không được khớp nhầm `metadata`, `metabolic`, `metaphor`..."""
    item = make(actors=["Metabolic Pathways Lab", "metadata team"])
    score_all([item], now=NOW)
    assert "known_org" not in item.score_breakdown

    real = make(actors=["Meta AI Research"])
    score_all([real], now=NOW)
    assert "known_org" in real.score_breakdown


def test_topics_are_inferred_from_keywords_when_absent() -> None:
    item = make(title="A retrieval-augmented agent for tool use")
    score_all([item], now=NOW)
    values = {t.value for t in item.topics}
    assert "rag" in values
    assert "agent" in values


def test_topic_match_bonus_applies_to_interests() -> None:
    interesting = make(title="An agent that plans with tool use")
    boring = make(title="A study of soil composition in northern regions")
    assert score(interesting) > score(boring)


def test_existing_topics_are_not_overwritten() -> None:
    from ai_radar.models import Topic

    item = make(title="A retrieval-augmented agent")
    item.topics = [Topic.SPEECH]
    score_all([item], now=NOW)
    assert item.topics == [Topic.SPEECH]


def test_zero_signals_do_not_appear_in_breakdown() -> None:
    """Chỉ giữ thành phần thực sự đóng góp, để bảng --explain còn đọc được."""
    item = make(age_days=0)
    score_all([item], now=NOW)
    assert "hf_upvotes" not in item.score_breakdown
    assert "github_stars" not in item.score_breakdown


def test_ranking_is_plausible_end_to_end() -> None:
    """Bài hot từ lab lớn kèm code phải xếp trên bài vô danh không tín hiệu."""
    hot = make(
        title="An agent framework for tool use",
        actors=["deepseek"],
        signals=Signals(hf_upvotes=280, is_daily_paper=True, has_code=True, github_stars=900),
    )
    obscure = make(title="Notes on lattice geometry", age_days=6)

    score_all([hot, obscure], now=NOW)
    assert hot.score > obscure.score


def test_explain_renders_components() -> None:
    item = make(signals=Signals(hf_upvotes=100, is_daily_paper=True))
    score_all([item], now=NOW)
    line = explain(item)
    assert "hf_upvotes" in line
    assert "is_daily_paper" in line
