"""Enricher dùng Gemini (Google AI Studio).

Chọn Gemini vì free tier thật, không cần thẻ tín dụng, và hạn mức dư xa nhu cầu
(~40 request/ngày).

API dùng `/v1beta/interactions`, KHÔNG phải `:generateContent` — endpoint sau đã
được Google đánh dấu legacy. Shape đã đối chiếu với tài liệu chính thức 2026-08:

    POST https://generativelanguage.googleapis.com/v1beta/interactions
    x-goog-api-key: <key>
    Api-Revision: 2026-05-20
    {"model": ..., "system_instruction": ..., "input": ...,
     "response_format": {"type": "text", "mime_type": "application/json",
                         "schema": {...}}}

Tên model để trong config vì Google đổi thế hệ khá nhanh (2.5 -> 3.x). Chạy
`python -m ai_radar --check-enrich` để xem key của bạn thực sự dùng được model nào.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
from typing import Any, ClassVar

import httpx

from ai_radar.enrich.base import Enricher, EnrichResult
from ai_radar.http import FetchError, get_json
from ai_radar.models import Item, Topic

logger = logging.getLogger(__name__)

API_URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
MODELS_URL = "https://generativelanguage.googleapis.com/v1beta/models"
API_REVISION = "2026-05-20"
ENV_KEY = "GEMINI_API_KEY"

SYSTEM_INSTRUCTION = """\
Bạn tóm tắt tin tức AI cho một kỹ sư người Việt đang theo dõi lĩnh vực này hằng ngày.

Quy tắc:
- Viết tiếng Việt tự nhiên. GIỮ NGUYÊN thuật ngữ kỹ thuật tiếng Anh đã phổ biến
  (transformer, fine-tune, benchmark, agent, embedding...) — đừng dịch cứng.
- `summary_vi`: 2-3 câu, nói CÁI GÌ MỚI và làm được gì. Không mở bài, không
  nhắc lại tiêu đề, không dùng cụm rỗng như "nghiên cứu này trình bày".
- `why_it_matters`: đúng MỘT câu về việc nó thay đổi gì trong thực tế. Nếu chỉ
  là cải tiến nhỏ thì nói thẳng như vậy.
- `topics`: chỉ chọn trong danh sách cho sẵn. Không có cái nào khớp thì trả về
  ["other"]. Đừng bịa tag mới.
- Chỉ dựa vào thông tin được cung cấp. Không suy diễn số liệu hay kết quả.\
"""

RESPONSE_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "summary_vi": {"type": "string", "description": "Tóm tắt tiếng Việt, 2-3 câu"},
        "why_it_matters": {"type": "string", "description": "Một câu về ý nghĩa thực tế"},
        "topics": {
            "type": "array",
            "items": {"type": "string", "enum": [t.value for t in Topic]},
        },
    },
    "required": ["summary_vi", "why_it_matters", "topics"],
}

SUMMARY_CHARS = 2000


class GeminiEnricher(Enricher):
    name: ClassVar[str] = "gemini"

    def __init__(
        self,
        api_key: str,
        model: str = "gemini-2.5-flash-lite",
        concurrency: int = 4,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.concurrency = max(1, concurrency)

    @property
    def headers(self) -> dict[str, str]:
        return {"x-goog-api-key": self.api_key, "Api-Revision": API_REVISION}

    async def enrich(self, client: httpx.AsyncClient, items: list[Item]) -> EnrichResult:
        pending = self.pending(items)
        result = EnrichResult(provider=self.name, requested=len(pending))
        if not pending:
            return result

        # Giới hạn số request song song để không chạm trần RPM của free tier.
        gate = asyncio.Semaphore(self.concurrency)

        async def one(item: Item) -> bool:
            async with gate:
                return await self._enrich_one(client, item)

        outcomes = await asyncio.gather(*(one(item) for item in pending))
        result.enriched = sum(outcomes)
        result.failed = len(outcomes) - result.enriched
        logger.info(
            "enrich (%s/%s): %d thành công, %d lỗi",
            self.name,
            self.model,
            result.enriched,
            result.failed,
        )
        return result

    async def _enrich_one(self, client: httpx.AsyncClient, item: Item) -> bool:
        try:
            payload = await self._call(client, _build_prompt(item))
            data = _extract_json(payload)
        except Exception as exc:  # noqa: BLE001 - nội dung là thứ có thì tốt
            logger.warning("enrich thất bại cho %r: %s", item.title[:50], exc)
            return False

        summary = str(data.get("summary_vi") or "").strip()
        if not summary:
            logger.warning("enrich trả về summary rỗng cho %r", item.title[:50])
            return False

        item.summary_vi = summary
        item.why_it_matters = str(data.get("why_it_matters") or "").strip() or None
        if topics := _parse_topics(data.get("topics")):
            item.topics = topics
        return True

    async def _call(self, client: httpx.AsyncClient, prompt: str) -> Any:
        request = client.build_request(
            "POST",
            API_URL,
            headers=self.headers,
            json={
                "model": self.model,
                "system_instruction": SYSTEM_INSTRUCTION,
                "input": prompt,
                "response_format": {
                    "type": "text",
                    "mime_type": "application/json",
                    "schema": RESPONSE_SCHEMA,
                },
            },
        )
        response = await client.send(request)
        if response.status_code >= 400:
            raise FetchError(f"HTTP {response.status_code}: {response.text[:200]}")
        return response.json()

    async def available_models(self, client: httpx.AsyncClient) -> list[str]:
        """Liệt kê model key này dùng được — cho cờ --check-enrich.

        Google đổi thế hệ model khá nhanh và trang rate limit giờ chỉ nói
        'xem trong AI Studio', nên để người dùng tự tra bằng chính key của mình
        vẫn chắc chắn hơn là hardcode một danh sách sẽ lỗi thời.
        """
        payload = await get_json(client, MODELS_URL, headers=self.headers)
        models = payload.get("models") if isinstance(payload, dict) else None
        if not isinstance(models, list):
            return []
        return sorted(
            str(m.get("name", "")).removeprefix("models/")
            for m in models
            if isinstance(m, dict) and m.get("name")
        )


def _build_prompt(item: Item) -> str:
    parts = [f"Loại: {item.kind.value}", f"Tiêu đề: {item.title}"]
    if item.actors:
        parts.append(f"Tác giả / tổ chức: {', '.join(item.actors[:6])}")
    if item.summary_en:
        parts.append(f"Mô tả gốc:\n{item.summary_en[:SUMMARY_CHARS]}")
    return "\n".join(parts)


def _extract_json(payload: Any) -> dict[str, Any]:
    """Lấy JSON kết quả ra khỏi response.

    Đường chính là `output_text`. Vẫn dò thêm shape lồng nhau vì tài liệu mô tả
    `output_text` như thuộc tính tiện dụng của SDK, chưa chắc REST thô luôn có.
    """
    text = _find_text(payload)
    if not text:
        raise ValueError(f"không tìm thấy text trong response: {str(payload)[:200]}")
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise ValueError(f"response không phải JSON hợp lệ: {text[:200]}") from exc
    if not isinstance(data, dict):
        raise TypeError(f"mong đợi object, nhận {type(data).__name__}")
    return data


def _find_text(payload: Any) -> str | None:
    if isinstance(payload, str):
        return payload or None
    if not isinstance(payload, dict):
        return None

    if isinstance(direct := payload.get("output_text"), str) and direct.strip():
        return direct

    # Shape lồng: output[].content[].text  hoặc  candidates[].content.parts[].text
    for container_key in ("output", "candidates"):
        for entry in payload.get(container_key) or []:
            if not isinstance(entry, dict):
                continue
            content = entry.get("content")
            blocks = content if isinstance(content, list) else []
            if isinstance(content, dict):
                blocks = content.get("parts") or []
            for block in blocks:
                if isinstance(block, dict) and isinstance(block.get("text"), str):
                    return str(block["text"])
    return None


def _parse_topics(raw: Any) -> list[Topic]:
    """Bỏ qua tag không hợp lệ thay vì để hỏng cả item."""
    if not isinstance(raw, list):
        return []
    topics: list[Topic] = []
    for value in raw:
        try:
            topic = Topic(str(value).strip().lower())
        except ValueError:
            logger.debug("bỏ qua topic không hợp lệ: %r", value)
            continue
        if topic not in topics:
            topics.append(topic)
    return topics


def from_env(model: str, concurrency: int) -> GeminiEnricher | None:
    key = os.environ.get(ENV_KEY, "").strip()
    if not key:
        return None
    return GeminiEnricher(api_key=key, model=model, concurrency=concurrency)
