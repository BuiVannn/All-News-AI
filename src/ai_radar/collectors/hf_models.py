"""Model mới ra mắt trên Hugging Face.

Chọn tham số sort sau khi thử cả bốn trên API thật (2026-08-01):

    sort=trending_score  -> HTTP 400. Tên đúng là camelCase `trendingScore`.
    sort=createdAt       -> toàn model rác, 0 download 0 like.
    sort=likes/downloads -> toàn model kinh điển nhiều năm tuổi (BERT, MiniLM).
    sort=trendingScore   -> Kimi-K3, DeepSeek-V4-Flash... đúng thứ cần.

Nên: lấy top trending rồi lọc lại theo `createdAt` để feed là "model MỚI ra",
không phải "model đang hot" (một model 2 năm tuổi vẫn có thể trending).

Dùng `expand[]` thay vì `full=true`: cùng lượng thông tin cần thiết nhưng
payload nhỏ hơn 6 lần (50KB so với 312KB ở limit=100), vì bỏ được `siblings`.
"""

from __future__ import annotations

import logging
from datetime import date, datetime, timedelta
from typing import Any, ClassVar

import httpx

from ai_radar import config
from ai_radar.collectors.base import Collector, parse_dt, utcnow
from ai_radar.http import get_json
from ai_radar.models import Item, Kind, Link, Signals, hf_key, make_id

logger = logging.getLogger(__name__)

API_URL = "https://huggingface.co/api/models"
EXPAND = [
    "author",
    "pipeline_tag",
    "createdAt",
    "downloads",
    "likes",
    "trendingScore",
    "tags",
    "library_name",
]
WEIGHT_TAGS = frozenset({"safetensors", "gguf", "pytorch", "onnx", "mlx", "transformers"})
BASE_MODEL_PREFIX = "base_model:"


class HFModelsCollector(Collector):
    name: ClassVar[str] = "hf_models"
    kind: ClassVar[Kind] = Kind.MODEL

    def __init__(
        self,
        limit: int | None = None,
        max_age_days: int | None = None,
        min_likes: int | None = None,
        skip_quantized: bool | None = None,
    ) -> None:
        cfg = config.section("hf_models")
        self.limit = limit if limit is not None else int(cfg.get("limit", 100))
        self.skip_quantized = (
            skip_quantized if skip_quantized is not None else bool(cfg.get("skip_quantized", True))
        )
        self.max_age_days = (
            max_age_days if max_age_days is not None else int(cfg.get("max_age_days", 30))
        )
        self.min_likes = min_likes if min_likes is not None else int(cfg.get("min_likes", 3))

    async def fetch(self, client: httpx.AsyncClient, day: date) -> list[Item]:
        payload = await get_json(
            client,
            API_URL,
            params={
                "sort": "trendingScore",
                "direction": -1,
                "limit": self.limit,
                "expand[]": EXPAND,
            },
        )
        if not isinstance(payload, list):
            raise TypeError(f"{self.name}: mong đợi list, nhận {type(payload).__name__}")

        cutoff = datetime.combine(day, datetime.min.time()).replace(
            tzinfo=utcnow().tzinfo
        ) - timedelta(days=self.max_age_days)

        items: list[Item] = []
        for raw in payload:
            try:
                item = self._parse(raw, cutoff)
            except Exception as exc:  # noqa: BLE001
                logger.warning("%s: bỏ qua record hỏng: %s", self.name, exc)
                continue
            if item is not None:
                items.append(item)
        return items

    def _parse(self, raw: dict[str, Any], cutoff: datetime) -> Item | None:
        repo_id = str(raw.get("id") or raw.get("modelId") or "").strip()
        if not repo_id:
            raise ValueError("thiếu id")

        likes = int(raw.get("likes") or 0)
        if likes < self.min_likes:
            return None

        created = parse_dt(raw.get("createdAt"))
        if created < cutoff:
            return None  # đang hot nhưng không mới -> không phải tin ra mắt

        tags = [str(t) for t in (raw.get("tags") or [])]
        relation, base_repo = _base_model(tags)

        # Bản lượng tử hoá KHÔNG phải tin ra mắt. Không lọc thì feed bị chiếm
        # chỗ: một lượt chạy thật cho ra 4 biến thể Kimi-K3 và 4 biến thể
        # Inkling trong top 30, đẩy hết paper và tin ra mắt ra ngoài.
        if self.skip_quantized and relation == "quantized":
            return None

        author = str(raw.get("author") or repo_id.split("/")[0])
        links = [
            Link(
                source="hf_models",
                url=f"https://huggingface.co/{repo_id}",
                external_id=repo_id,
            )
        ]
        # Finetune vẫn là tin ra mắt thật (microsoft/Fara1.5-27B fine-tune từ
        # Qwen3.5-27B), nên giữ lại và nối thêm link tới model gốc.
        if base_repo:
            links.append(
                Link(
                    source=f"hf_base_model:{relation or 'base'}",
                    url=f"https://huggingface.co/{base_repo}",
                    external_id=base_repo,
                )
            )

        return Item(
            id=make_id(hf_key(repo_id)),
            kind=self.kind,
            title=repo_id,
            summary_en=_describe(raw, tags),
            links=links,
            actors=[author],
            published_at=created,
            first_seen_at=utcnow(),
            # KHÔNG dùng title_key cho model: `unsloth/Kimi-K3-GGUF` là bản
            # quantize của `moonshotai/Kimi-K3` — hai thứ khác nhau, gộp là sai.
            # Cũng KHÔNG dùng hf_key(base_repo) làm khoá gộp, vì như vậy bản
            # phái sinh sẽ nuốt luôn model gốc.
            dedup_keys=[hf_key(repo_id)],
            signals=Signals(
                hf_likes=likes,
                hf_downloads=int(raw.get("downloads") or 0),
                hf_trending_score=float(raw.get("trendingScore") or 0.0),
                has_weights=any(t in WEIGHT_TAGS for t in tags),
            ),
        )


def _base_model(tags: list[str]) -> tuple[str | None, str | None]:
    """Đọc quan hệ model gốc từ tag của HF.

    HF công bố quan hệ này ngay trong tag, nên không cần đoán theo tên repo:
        base_model:moonshotai/Kimi-K3
        base_model:quantized:moonshotai/Kimi-K3
        base_model:finetune:Qwen/Qwen3.5-27B

    Trả về (quan hệ, repo gốc). Quan hệ là None khi chỉ có dạng `base_model:<repo>`.
    """
    relation: str | None = None
    base: str | None = None
    for tag in tags:
        if not tag.startswith(BASE_MODEL_PREFIX):
            continue
        rest = tag[len(BASE_MODEL_PREFIX) :]
        head, sep, tail = rest.partition(":")
        if sep and "/" in tail:
            relation, base = head.lower(), tail
        elif "/" in rest and base is None:
            base = rest
    return relation, base


def _describe(raw: dict[str, Any], tags: list[str]) -> str | None:
    """API không trả model card, nên dựng một dòng mô tả từ metadata sẵn có."""
    parts = []
    if pipeline := raw.get("pipeline_tag"):
        parts.append(str(pipeline))
    if library := raw.get("library_name"):
        parts.append(str(library))
    visible = [t for t in tags if ":" not in t and t not in WEIGHT_TAGS][:6]
    parts.extend(visible)
    return ", ".join(dict.fromkeys(parts)) or None
