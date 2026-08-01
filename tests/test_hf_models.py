"""HF Models — model mới ra mắt.

Fixture là bản chụp thật, chọn có chủ đích để phủ các trường hợp khó:
cặp base/GGUF (bẫy dedup), model 2024 (bộ lọc tuổi), model ít like.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx

from ai_radar.collectors.hf_models import API_URL, HFModelsCollector
from ai_radar.http import build_client
from ai_radar.models import Item, Kind

FIXTURES = Path(__file__).parent / "fixtures"
DAY = date(2026, 8, 1)


@pytest.fixture
def payload() -> list[dict[str, Any]]:
    data: list[dict[str, Any]] = json.loads(
        (FIXTURES / "hf_models.json").read_text(encoding="utf-8")
    )
    return data


async def _call(payload: Any, **kwargs: Any) -> tuple[list[Item], httpx.Request]:
    collector = HFModelsCollector(**kwargs)
    with respx.mock:
        route = respx.get(API_URL).mock(return_value=httpx.Response(200, json=payload))
        async with build_client() as client:
            items = await collector.fetch(client, DAY)
    return items, route.calls[0].request


async def _fetch(payload: Any, **kwargs: Any) -> list[Item]:
    items, _ = await _call(payload, **kwargs)
    return items


async def test_uses_camelcase_trending_sort(payload: list[dict[str, Any]]) -> None:
    """`trending_score` trả HTTP 400; tên đúng là `trendingScore`."""
    _, request = await _call(payload)
    query = str(request.url)
    assert "sort=trendingScore" in query
    assert "trending_score" not in query


async def test_requests_expand_not_full(payload: list[dict[str, Any]]) -> None:
    """`expand[]` cho payload nhỏ hơn 6 lần so với `full=true` (50KB vs 312KB)."""
    _, request = await _call(payload)
    query = str(request.url)
    assert "expand" in query
    assert "full=true" not in query


async def test_old_model_is_filtered_even_when_trending(
    payload: list[dict[str, Any]],
) -> None:
    """FLUX.1-dev (2024) rất hot nhưng không MỚI — feed là tin ra mắt."""
    items = await _fetch(payload, max_age_days=30)
    assert not any("FLUX.1-dev" in i.title for i in items)

    everything = await _fetch(payload, max_age_days=3650)
    assert any("FLUX.1-dev" in i.title for i in everything)


async def test_low_like_models_are_filtered(payload: list[dict[str, Any]]) -> None:
    items = await _fetch(payload, max_age_days=3650, min_likes=1000)
    assert items
    assert all(i.signals.hf_likes >= 1000 for i in items)


async def test_quantized_derivative_is_not_merged_with_base(
    payload: list[dict[str, Any]],
) -> None:
    """`unsloth/DeepSeek-V4-Flash-0731-GGUF` là bản quantize, KHÔNG phải bản gốc.

    Vì vậy model cố tình không phát khoá `title:` — gộp chúng lại là sai.
    """
    items = await _fetch(payload, max_age_days=3650, skip_quantized=False)
    base = next(i for i in items if i.title == "deepseek-ai/DeepSeek-V4-Flash-0731")
    gguf = next(i for i in items if i.title == "unsloth/DeepSeek-V4-Flash-0731-GGUF")

    assert base.id != gguf.id
    assert not set(base.dedup_keys) & set(gguf.dedup_keys)
    assert all(not k.startswith("title:") for k in base.dedup_keys)


async def test_quantized_repacks_are_skipped_by_default(
    payload: list[dict[str, Any]],
) -> None:
    """Bản GGUF không phải tin ra mắt — để lọt thì feed bị biến thể chiếm chỗ.

    Trên dữ liệu thật, không lọc thì top 30 có 4 biến thể Kimi-K3 và 4 biến thể
    Inkling, đẩy hết paper và tin ra mắt ra ngoài.
    """
    kept = await _fetch(payload, max_age_days=3650)
    titles = {i.title for i in kept}

    assert "unsloth/DeepSeek-V4-Flash-0731-GGUF" not in titles
    assert "deepseek-ai/DeepSeek-V4-Flash-0731" in titles


async def test_finetunes_are_kept_and_linked_to_base(
    payload: list[dict[str, Any]],
) -> None:
    """Fine-tune là tin ra mắt thật, chỉ bản lượng tử hoá mới bị bỏ."""
    items = await _fetch(payload, max_age_days=3650, skip_quantized=False)
    gguf = next(i for i in items if i.title == "unsloth/DeepSeek-V4-Flash-0731-GGUF")

    base_link = next(link for link in gguf.links if link.source.startswith("hf_base_model"))
    assert base_link.external_id == "deepseek-ai/DeepSeek-V4-Flash-0731"
    assert "quantized" in base_link.source


def test_base_model_tag_is_parsed() -> None:
    from ai_radar.collectors.hf_models import _base_model

    assert _base_model(["base_model:quantized:moonshotai/Kimi-K3"]) == (
        "quantized",
        "moonshotai/Kimi-K3",
    )
    assert _base_model(["base_model:finetune:Qwen/Qwen3.5-27B"]) == (
        "finetune",
        "Qwen/Qwen3.5-27B",
    )
    assert _base_model(["base_model:org/model"]) == (None, "org/model")
    assert _base_model(["transformers", "safetensors"]) == (None, None)


async def test_maps_signals_and_metadata(payload: list[dict[str, Any]]) -> None:
    item = next(
        i for i in await _fetch(payload, max_age_days=3650) if i.title == "moonshotai/Kimi-K3"
    )

    assert item.kind is Kind.MODEL
    assert item.actors == ["moonshotai"]
    assert item.links[0].url == "https://huggingface.co/moonshotai/Kimi-K3"
    assert item.signals.hf_likes > 0
    assert item.signals.hf_downloads > 0
    assert item.signals.hf_trending_score > 0
    assert item.signals.has_weights is True
    assert item.dedup_keys == ["hf:moonshotai/kimi-k3"]


async def test_broken_record_does_not_lose_the_batch(
    payload: list[dict[str, Any]],
) -> None:
    clean = await _fetch(payload, max_age_days=3650, skip_quantized=False)
    withbad = await _fetch([{"likes": 999}, *payload], max_age_days=3650, skip_quantized=False)
    assert len(withbad) == len(clean)


async def test_non_list_payload_raises() -> None:
    with pytest.raises(TypeError):
        await _fetch({"error": "nope"})
