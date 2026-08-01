"""CLI: python -m ai_radar [--date YYYY-MM-DD] [--limit N] [--dry-run]"""

from __future__ import annotations

import argparse
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
    parser.add_argument("-v", "--verbose", action="store_true")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)-7s %(message)s",
    )

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
