"""Gộp chéo nguồn — phần tạo ra giá trị của dự án.

Rủi ro chính là gộp NHẦM: hai thứ khác nhau bị nhập làm một thì người dùng
mất hẳn một mục và không có cách nào phát hiện. Vì vậy số test chống gộp nhầm
nhiều hơn số test chứng minh gộp đúng.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from ai_radar.dedup import merge
from ai_radar.models import Item, Kind, Link, Signals, title_key

BASE = datetime(2026, 7, 29, tzinfo=UTC)


def make(
    item_id: str,
    *,
    kind: Kind = Kind.PAPER,
    keys: list[str],
    links: list[tuple[str, str]] | None = None,
    days: int = 0,
    title: str = "",
    signals: Signals | None = None,
    actors: list[str] | None = None,
    summary: str | None = None,
) -> Item:
    return Item(
        id=item_id,
        kind=kind,
        title=title or f"Paper {item_id}",
        summary_en=summary,
        links=[Link(source=s, url=u) for s, u in (links or [])],
        actors=actors or [],
        published_at=BASE + timedelta(days=days),
        first_seen_at=BASE + timedelta(days=days),
        dedup_keys=keys,
        signals=signals or Signals(),
    )


# --------------------------------------------------------------------------
# Gộp đúng
# --------------------------------------------------------------------------


def test_same_paper_from_arxiv_and_hf_becomes_one_item_with_both_links() -> None:
    """Đây chính là điều dự án hứa hẹn: một mục, nhiều đường dẫn."""
    items = [
        make("a", keys=["arxiv:2607.11111"], links=[("arxiv", "https://arxiv.org/abs/2607.11111")]),
        make(
            "b",
            keys=["arxiv:2607.11111"],
            links=[("hf_papers", "https://huggingface.co/papers/2607.11111")],
        ),
    ]
    merged, removed = merge(items)

    assert len(merged) == 1
    assert removed == 1
    assert {link.source for link in merged[0].links} == {"arxiv", "hf_papers"}


def test_transitive_merge_across_three_sources() -> None:
    """arXiv↔HF qua arXiv ID, HF↔GitHub qua repo — cả ba phải về một nhóm."""
    items = [
        make("a", keys=["arxiv:2607.11111"], links=[("arxiv", "https://arxiv.org/abs/x")]),
        make(
            "b",
            keys=["arxiv:2607.11111", "github:acme/tool"],
            links=[("hf_papers", "https://huggingface.co/papers/x")],
        ),
        make("c", keys=["github:acme/tool"], links=[("github", "https://github.com/acme/tool")]),
    ]
    merged, removed = merge(items)

    assert len(merged) == 1
    assert removed == 2
    assert len(merged[0].links) == 3


def test_merges_on_doi_and_on_url() -> None:
    by_doi, _ = merge(
        [make("a", keys=["doi:10.1/x"]), make("b", keys=["doi:10.1/x"])]
    )
    by_url, _ = merge(
        [
            make("a", kind=Kind.RELEASE, keys=["url:openai.com/post"]),
            make("b", kind=Kind.RELEASE, keys=["url:openai.com/post"]),
        ]
    )
    assert len(by_doi) == 1
    assert len(by_url) == 1


def test_merges_identical_titles_reordered_and_punctuated() -> None:
    items = [
        make(
            "a",
            keys=[title_key("Attention Is All You Need!")],
            title="Attention Is All You Need",
        ),
        make("b", keys=[title_key("attention need all you is")], title="Attention (reprint)"),
    ]
    merged, _ = merge(items)
    assert len(merged) == 1


def test_fuzzy_title_merges_near_identical_titles() -> None:
    left = "Sparse Routing Improves Long Context Retrieval in Language Models"
    right = "Sparse Routing Improves Long Context Retrieval for Language Models"
    merged, _ = merge([
        make("a", keys=[title_key(left)], title=left),
        make("b", keys=[title_key(right)], title=right),
    ])
    assert len(merged) == 1


# --------------------------------------------------------------------------
# Chống gộp nhầm — quan trọng hơn
# --------------------------------------------------------------------------


def test_quantized_model_is_not_merged_with_base_model() -> None:
    """`unsloth/Kimi-K3-GGUF` và `moonshotai/Kimi-K3` là hai thứ khác nhau."""
    items = [
        make("a", kind=Kind.MODEL, keys=["hf:moonshotai/kimi-k3"], title="moonshotai/Kimi-K3"),
        make("b", kind=Kind.MODEL, keys=["hf:unsloth/kimi-k3-gguf"], title="unsloth/Kimi-K3-GGUF"),
    ]
    merged, removed = merge(items)
    assert len(merged) == 2
    assert removed == 0


def test_same_title_outside_time_window_is_not_merged() -> None:
    """Bài trùng tên cách nhau nhiều năm không phải cùng một bài."""
    key = title_key("A Survey of Reinforcement Learning")
    items = [make("a", keys=[key], days=0), make("b", keys=[key], days=400)]

    assert len(merge(items, title_window_days=7)[0]) == 2
    assert len(merge(items, title_window_days=500)[0]) == 1


def test_same_title_different_kind_is_not_merged() -> None:
    """Paper tên X và model tên X là hai mục khác nhau."""
    key = title_key("Gemma Scope Interpretability")
    items = [
        make("a", kind=Kind.PAPER, keys=[key]),
        make("b", kind=Kind.MODEL, keys=[key]),
    ]
    assert len(merge(items)[0]) == 2


def test_unrelated_items_are_left_alone() -> None:
    items = [
        make("a", keys=["arxiv:2607.11111"]),
        make("b", keys=["arxiv:2607.22222"]),
        make("c", keys=["hf:org/model"], kind=Kind.MODEL),
    ]
    merged, removed = merge(items)
    assert len(merged) == 3
    assert removed == 0


def test_different_titles_are_not_fuzzy_merged() -> None:
    left = "Sparse Routing for Long Context Retrieval"
    right = "Dense Captioning of Satellite Imagery Datasets"
    merged, _ = merge([
        make("a", keys=[title_key(left)], title=left),
        make("b", keys=[title_key(right)], title=right),
    ])
    assert len(merged) == 2


# --------------------------------------------------------------------------
# Cách hợp nhất nội dung khi đã gộp
# --------------------------------------------------------------------------


def test_keeps_earliest_published_as_primary() -> None:
    """Bài arXiv gốc là bản chính, không phải bài blog viết lại sau đó."""
    items = [
        make("blog", keys=["arxiv:2607.1"], days=3, title="Bài blog viết lại"),
        make("paper", keys=["arxiv:2607.1"], days=0, title="Paper gốc"),
    ]
    merged, _ = merge(items)
    assert merged[0].title == "Paper gốc"


def test_signals_take_the_maximum_across_sources() -> None:
    """Nguồn nào biết nhiều hơn thì thắng — không được mất tín hiệu khi gộp."""
    items = [
        make("a", keys=["arxiv:2607.1"], signals=Signals(hf_upvotes=200, has_code=False)),
        make("b", keys=["arxiv:2607.1"], signals=Signals(github_stars=90, has_code=True)),
    ]
    merged, _ = merge(items)

    assert merged[0].signals.hf_upvotes == 200
    assert merged[0].signals.github_stars == 90
    assert merged[0].signals.has_code is True


def test_fills_missing_summary_and_unions_actors_and_keys() -> None:
    items = [
        make("a", keys=["arxiv:2607.1"], actors=["Mai Tran"], summary=None),
        make("b", keys=["arxiv:2607.1", "github:acme/x"], actors=["Kenji W"], summary="Tóm tắt"),
    ]
    merged, _ = merge(items)

    assert merged[0].summary_en == "Tóm tắt"
    assert merged[0].actors == ["Mai Tran", "Kenji W"]
    assert "github:acme/x" in merged[0].dedup_keys


def test_duplicate_urls_are_not_repeated() -> None:
    url = "https://arxiv.org/abs/2607.1"
    items = [
        make("a", keys=["arxiv:2607.1"], links=[("arxiv", url)]),
        make("b", keys=["arxiv:2607.1"], links=[("arxiv", url), ("hf_papers", "https://hf.co/x")]),
    ]
    merged, _ = merge(items)
    assert [link.url for link in merged[0].links] == [url, "https://hf.co/x"]


def test_empty_and_single_input_are_handled() -> None:
    assert merge([]) == ([], 0)
    single = [make("a", keys=["arxiv:1"])]
    assert merge(single) == (single, 0)
