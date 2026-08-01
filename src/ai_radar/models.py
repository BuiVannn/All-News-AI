"""Schema dùng chung cho toàn bộ pipeline.

Mọi collector đều chuẩn hoá về `Item`. Đây là hợp đồng duy nhất giữa các tầng:
collector -> dedup -> scoring -> enrich -> store -> web.
"""

from __future__ import annotations

import hashlib
import re
from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, Field


class Kind(StrEnum):
    """Loại sự kiện. Quyết định cách hiển thị trên web."""

    PAPER = "paper"
    MODEL = "model"
    RELEASE = "release"  # tin ra mắt từ blog chính thức
    REPO = "repo"
    TOOL = "tool"  # MCP server, skill, agent framework


class Topic(StrEnum):
    """Tag chủ đề. Enum đóng để tier-2 (LLM) không tự bịa tag mới."""

    LLM = "llm"
    CV = "cv"
    SPEECH = "speech"
    MULTIMODAL = "multimodal"
    AGENT = "agent"
    RAG = "rag"
    MCP = "mcp"
    ROBOTICS = "robotics"
    INFRA = "infra"
    EVAL = "eval"
    OTHER = "other"


class Link(BaseModel):
    """Một đường dẫn tới item này ở một nguồn cụ thể.

    `Item.links` là mảng vì cùng một sự kiện thường xuất hiện ở nhiều nguồn
    (arXiv + HF + GitHub + blog). Gộp chúng lại chính là giá trị cốt lõi.
    """

    source: str
    url: str
    external_id: str | None = None


class Signals(BaseModel):
    """Tín hiệu thô dùng cho tier-1 scoring. Luôn có giá trị mặc định."""

    hf_upvotes: int = 0
    hf_likes: int = 0
    hf_downloads: int = 0
    hf_trending_score: float = 0.0
    is_daily_paper: bool = False
    github_stars: int = 0
    github_stars_delta: int = 0
    hn_points: int = 0
    reddit_score: int = 0
    num_comments: int = 0
    has_code: bool = False
    has_weights: bool = False


class Item(BaseModel):
    """Một mục trong feed."""

    id: str
    kind: Kind
    title: str
    summary_en: str | None = None

    # Tier-2 (LLM) điền các trường dưới đây. None = chưa enrich.
    summary_vi: str | None = None
    why_it_matters: str | None = None
    topics: list[Topic] = Field(default_factory=list)

    links: list[Link] = Field(default_factory=list)
    actors: list[str] = Field(default_factory=list)

    published_at: datetime
    first_seen_at: datetime

    # Khoá dùng để gộp item trùng giữa các nguồn. Xem docs/ARCHITECTURE.md §5.
    dedup_keys: list[str] = Field(default_factory=list)

    signals: Signals = Field(default_factory=Signals)
    score: float = 0.0
    score_breakdown: dict[str, float] = Field(default_factory=dict)


class SourceResult(BaseModel):
    """Kết quả của một nguồn trong một lượt chạy."""

    source: str
    ok: bool
    fetched: int = 0
    error: str | None = None
    duration_s: float = 0.0


class RunManifest(BaseModel):
    """Nhật ký một lượt chạy — ghi ra data/runs/YYYY-MM-DD.json.

    Vừa để debug ("hôm qua sao ít bài thế?"), vừa là bằng chứng pipeline
    xử lý lỗi tử tế thay vì im lặng nuốt exception.
    """

    day: str
    started_at: datetime
    finished_at: datetime
    sources: list[SourceResult] = Field(default_factory=list)
    fetched: int = 0
    new: int = 0
    duplicates: int = 0
    merged: int = 0

    @property
    def failed_sources(self) -> list[str]:
        return [s.source for s in self.sources if not s.ok]


# --------------------------------------------------------------------------
# Khoá dedup
# --------------------------------------------------------------------------

_ARXIV_VERSION = re.compile(r"v\d+$")
_TRACKING_PARAMS = ("utm_", "ref", "ref_src", "fbclid", "gclid")


def make_id(*parts: str) -> str:
    """ID ổn định giữa các lần chạy — cùng input luôn cho cùng output."""
    key = "|".join(p.strip().lower() for p in parts if p)
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def arxiv_key(arxiv_id: str) -> str:
    """`2508.01234v3` -> `arxiv:2508.01234`.

    Bỏ hậu tố version, nếu không v1 và v3 của cùng một paper sẽ thành hai item.
    """
    clean = _ARXIV_VERSION.sub("", arxiv_id.strip().lower())
    return f"arxiv:{clean}"


def doi_key(doi: str) -> str:
    clean = doi.strip().lower()
    for prefix in ("https://doi.org/", "http://doi.org/", "doi:"):
        clean = clean.removeprefix(prefix)
    return f"doi:{clean}"


def github_key(url_or_name: str) -> str:
    """Nhận cả URL đầy đủ lẫn `owner/repo`, trả về `github:owner/repo`."""
    text = url_or_name.strip().lower().rstrip("/")
    text = text.removesuffix(".git")
    match = re.search(r"github\.com/([^/]+/[^/]+)", text)
    name = match.group(1) if match else text
    return f"github:{name}"


def hf_key(repo_id: str) -> str:
    return f"hf:{repo_id.strip().lower().strip('/')}"


def url_key(url: str) -> str:
    """Chuẩn hoá URL: bỏ scheme, `www.`, tracking params, trailing slash."""
    text = url.strip().lower()
    text = re.sub(r"^https?://", "", text)
    text = text.removeprefix("www.")
    if "?" in text:
        base, _, query = text.partition("?")
        kept = [
            part
            for part in query.split("&")
            if part and not part.startswith(_TRACKING_PARAMS)
        ]
        text = base + ("?" + "&".join(kept) if kept else "")
    return f"url:{text.rstrip('/')}"


def title_key(title: str) -> str:
    """Khoá mờ theo tiêu đề — chỉ dùng trong cửa sổ ±7 ngày (xem dedup.py)."""
    text = re.sub(r"[^a-z0-9 ]+", " ", title.strip().lower())
    tokens = sorted(t for t in text.split() if len(t) > 2)
    return "title:" + " ".join(tokens)
