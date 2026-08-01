"""HTTP có retry, backoff và tôn trọng rate limit.

Mọi collector đều đi qua đây. Tập trung logic retry vào một chỗ để không phải
lặp lại ở từng nguồn, và để chính sách rate limit sửa được ở một nơi duy nhất.
"""

from __future__ import annotations

import asyncio
import logging
import random
from typing import Any

import httpx

logger = logging.getLogger(__name__)

USER_AGENT = "ai-radar/0.1 (+https://github.com/BuiVannn/ai-radar)"
DEFAULT_TIMEOUT = 30.0
RETRY_STATUS = frozenset({429, 500, 502, 503, 504})


class FetchError(RuntimeError):
    """Nguồn không trả được dữ liệu sau khi đã retry hết."""


def build_client(timeout: float = DEFAULT_TIMEOUT) -> httpx.AsyncClient:
    return httpx.AsyncClient(
        timeout=timeout,
        headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
        follow_redirects=True,
    )


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    """Ưu tiên header `Retry-After` của server; nếu không có thì backoff mũ + jitter."""
    if response is not None:
        raw = response.headers.get("Retry-After")
        if raw:
            try:
                return min(float(raw), 60.0)
            except ValueError:
                pass
    return min(2.0**attempt, 30.0) + random.uniform(0, 1)


async def get_bytes(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    attempts: int = 3,
) -> bytes:
    """GET nội dung thô — dùng cho RSS/Atom.

    Cố tình tự tải rồi mới đưa cho feedparser, thay vì để `feedparser.parse(url)`
    tự gọi mạng: như vậy RSS mới đi qua cùng một lớp retry/backoff/User-Agent
    như mọi nguồn khác.
    """
    response = await _request(client, url, params=params, attempts=attempts)
    return response.content


async def get_json(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    attempts: int = 3,
) -> Any:
    """GET một endpoint JSON."""
    response = await _request(client, url, params=params, attempts=attempts)
    try:
        return response.json()
    except ValueError as exc:
        raise FetchError(f"GET {url}: body không phải JSON hợp lệ: {exc}") from exc


async def _request(
    client: httpx.AsyncClient,
    url: str,
    *,
    params: dict[str, Any] | None = None,
    attempts: int = 3,
) -> httpx.Response:
    """GET có retry.

    Dùng GET chứ không POST một cách có chủ đích: nhiều nguồn (đáng chú ý là
    arXiv) đặt CDN cache trước GET, nên GET vừa nhanh hơn vừa ít dính rate
    limit hơn hẳn.
    """
    last_error: Exception | None = None

    for attempt in range(attempts):
        response: httpx.Response | None = None
        try:
            response = await client.get(url, params=params)
            if response.status_code in RETRY_STATUS:
                raise httpx.HTTPStatusError(
                    f"HTTP {response.status_code}", request=response.request, response=response
                )
            response.raise_for_status()
            return response
        except httpx.HTTPError as exc:
            last_error = exc
            retryable = response is None or response.status_code in RETRY_STATUS
            if not retryable or attempt == attempts - 1:
                break
            delay = _retry_delay(response, attempt)
            logger.warning(
                "GET %s thất bại (%s), thử lại sau %.1fs [%d/%d]",
                url,
                exc,
                delay,
                attempt + 1,
                attempts,
            )
            await asyncio.sleep(delay)

    raise FetchError(f"GET {url} thất bại sau {attempts} lần: {last_error}") from last_error
