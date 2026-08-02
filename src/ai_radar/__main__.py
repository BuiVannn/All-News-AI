"""CLI: python -m ai_radar [--date YYYY-MM-DD] [--limit N] [--dry-run] [--explain]"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from datetime import date

from ai_radar.pipeline import DEFAULT_LIMIT, run


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ai-radar", description="Thu thập feed AI trong ngày.")
    parser.add_argument(
        "--date",
        type=date.fromisoformat,
        default=None,
        help="Ngày cần thu thập (YYYY-MM-DD). Mặc định: hôm nay theo UTC.",
    )
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT, help="Số item tối đa giữ lại.")
    parser.add_argument("--dry-run", action="store_true", help="Không ghi gì xuống data/.")
    parser.add_argument(
        "--explain", action="store_true", help="In bảng phân rã điểm của từng item."
    )
    parser.add_argument(
        "--check-enrich",
        action="store_true",
        help="Kiểm tra cấu hình enrich và liệt kê model API key hiện dùng được.",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def _check_enrich() -> int:
    """Tra xem key hiện tại dùng được model nào.

    Google đổi thế hệ model khá nhanh và trang rate limit giờ chỉ nói "xem trong
    AI Studio", nên để người dùng tra bằng chính key của mình chắc chắn hơn là
    tin vào một danh sách hardcode sẽ lỗi thời.
    """
    from ai_radar import config
    from ai_radar.enrich import GeminiEnricher, build_enricher
    from ai_radar.http import build_client

    enricher = build_enricher()
    configured = str(config.section("enrich").get("model") or "")
    print(f"provider : {enricher.name}")
    print(f"model    : {configured or '(không có)'}")

    if not isinstance(enricher, GeminiEnricher):
        print(
            "\nChưa bật enrich. Feed vẫn chạy nhưng không có tóm tắt tiếng Việt.\n"
            "Bật bằng cách: lấy key tại https://aistudio.google.com/apikey\n"
            "rồi export GEMINI_API_KEY=<key>"
        )
        return 0

    async def _list() -> list[str]:
        async with build_client() as client:
            return await enricher.available_models(client)

    try:
        models = asyncio.run(_list())
    except Exception as exc:  # noqa: BLE001
        print(f"\nKhông liệt kê được model: {exc}")
        return 1

    usable = [m for m in models if "flash" in m or "pro" in m]
    print(f"\nKey dùng được {len(models)} model. Nhóm flash/pro:")
    for name in usable:
        mark = " <- đang cấu hình" if name == configured else ""
        print(f"  {name}{mark}")

    if configured and configured not in models:
        print(
            f"\nCẢNH BÁO: '{configured}' không có trong danh sách. "
            f"Sửa enrich.model trong config/sources.yaml."
        )
        return 1
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-7s %(message)s",
    )

    if args.check_enrich:
        return _check_enrich()

    day = args.date or date.today()
    manifest = run(day, limit=args.limit, dry_run=args.dry_run)

    print(
        f"\n{day}  fetched={manifest.fetched}  new={manifest.new}  "
        f"gộp={manifest.merged}  trùng={manifest.duplicates}"
    )
    for source in manifest.sources:
        mark = "ok " if source.ok else "LỖI"
        detail = f"{source.fetched} item" if source.ok else (source.error or "")
        print(f"  [{mark}] {source.source:<14} {source.duration_s:>5.2f}s  {detail}")

    if enrichment := manifest.enrichment:
        print(
            f"  [enrich] {enrichment.provider:<12} "
            f"{enrichment.enriched} tóm tắt, {enrichment.failed} lỗi, "
            f"{enrichment.skipped} bỏ qua"
        )

    if args.explain:
        from ai_radar import store
        from ai_radar.scoring import explain

        print()
        for item in store.read_items(day):
            print("  " + explain(item))

    if manifest.failed_sources:
        print(f"\nNguồn lỗi: {', '.join(manifest.failed_sources)}")

    # Chỉ báo lỗi khi TẤT CẢ nguồn đều chết. Một nguồn chết là chuyện bình
    # thường và không nên làm đỏ CI, nếu không cảnh báo sẽ mất tác dụng.
    if manifest.sources and not any(s.ok for s in manifest.sources):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
