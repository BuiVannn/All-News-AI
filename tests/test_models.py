"""Khoá dedup phải chuẩn hoá đúng — đây là nền của việc gộp chéo nguồn."""

from __future__ import annotations

import pytest

from ai_radar.models import arxiv_key, doi_key, github_key, make_id, title_key, url_key


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("2508.01234", "arxiv:2508.01234"),
        ("2508.01234v1", "arxiv:2508.01234"),
        ("2508.01234v13", "arxiv:2508.01234"),
        ("  2508.01234V2  ", "arxiv:2508.01234"),
    ],
)
def test_arxiv_key_strips_version(raw: str, expected: str) -> None:
    """v1 và v3 của cùng một paper phải gộp làm một."""
    assert arxiv_key(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "https://github.com/MAC-AutoML/OmniScope",
        "https://github.com/MAC-AutoML/OmniScope/",
        "https://github.com/MAC-AutoML/OmniScope.git",
        "http://www.github.com/mac-automl/omniscope",
        "MAC-AutoML/OmniScope",
    ],
)
def test_github_key_normalises_all_forms(raw: str) -> None:
    assert github_key(raw) == "github:mac-automl/omniscope"


def test_doi_key_strips_prefixes() -> None:
    assert doi_key("https://doi.org/10.1234/ABC") == "doi:10.1234/abc"
    assert doi_key("doi:10.1234/abc") == "doi:10.1234/abc"


def test_url_key_drops_tracking_params_but_keeps_real_ones() -> None:
    assert url_key("https://www.example.com/post/?utm_source=x") == "url:example.com/post"
    assert url_key("https://example.com/p?id=7&utm_medium=y") == "url:example.com/p?id=7"


def test_title_key_ignores_word_order_and_punctuation() -> None:
    """Cùng một paper được đăng lại với tiêu đề xáo trộn nhẹ vẫn phải khớp."""
    assert title_key("Attention Is All You Need!") == title_key("attention need all you is")


def test_title_key_drops_short_tokens() -> None:
    assert "is" not in title_key("Attention Is All You Need")


def test_make_id_is_stable_and_distinct() -> None:
    assert make_id("arxiv:2508.01234") == make_id("arxiv:2508.01234")
    assert make_id("arxiv:2508.01234") != make_id("arxiv:2508.01235")
    assert len(make_id("x")) == 16
