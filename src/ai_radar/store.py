"""Đọc/ghi thư mục data/.

Bố cục (xem docs/ARCHITECTURE.md §3.2):
    data/items/YYYY-MM-DD.json   item đã qua lọc, là nguồn dữ liệu cho web
    data/seen/YYYY-MM.txt        sổ ID đã gặp — plaintext append-only
    data/runs/YYYY-MM-DD.json    nhật ký chạy

Sổ `seen` cố tình là plaintext chứ không phải SQLite: file binary đổi mỗi
ngày làm git phình rất nhanh, còn file text chỉ-thêm cho diff nhỏ xíu.
"""

from __future__ import annotations

import json
from datetime import date
from pathlib import Path

from ai_radar.models import Item, RunManifest

DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def items_path(day: date, root: Path | None = None) -> Path:
    return (root or DATA_DIR) / "items" / f"{day.isoformat()}.json"


def run_path(day: date, root: Path | None = None) -> Path:
    return (root or DATA_DIR) / "runs" / f"{day.isoformat()}.json"


def seen_path(day: date, root: Path | None = None) -> Path:
    return (root or DATA_DIR) / "seen" / f"{day.strftime('%Y-%m')}.txt"


def _write(path: Path, text: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def write_items(day: date, items: list[Item], root: Path | None = None) -> Path:
    """Ghi feed của một ngày. Sắp xếp theo score giảm dần cho web đọc thẳng."""
    ordered = sorted(items, key=lambda i: (-i.score, i.title))
    payload = [json.loads(i.model_dump_json()) for i in ordered]
    return _write(
        items_path(day, root), json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    )


def read_items(day: date, root: Path | None = None) -> list[Item]:
    path = items_path(day, root)
    if not path.exists():
        return []
    return [Item.model_validate(row) for row in json.loads(path.read_text(encoding="utf-8"))]


def write_run(manifest: RunManifest, root: Path | None = None) -> Path:
    day = date.fromisoformat(manifest.day)
    return _write(run_path(day, root), manifest.model_dump_json(indent=2) + "\n")


def load_seen(root: Path | None = None) -> set[str]:
    """Nạp toàn bộ sổ ID đã gặp (mọi tháng).

    Ở quy mô vài trăm nghìn dòng thì đọc hết vẫn nhanh hơn nhiều so với việc
    dựng index. Khi nào chậm thật mới tối ưu.
    """
    seen_dir = (root or DATA_DIR) / "seen"
    if not seen_dir.exists():
        return set()
    ids: set[str] = set()
    for path in sorted(seen_dir.glob("*.txt")):
        ids.update(
            line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()
        )
    return ids


def append_seen(day: date, ids: list[str], root: Path | None = None) -> Path:
    """Ghi thêm ID vào sổ của tháng. Bỏ qua ID đã có trong chính file đó."""
    path = seen_path(day, root)
    path.parent.mkdir(parents=True, exist_ok=True)

    existing: set[str] = set()
    if path.exists():
        existing = {
            line.strip()
            for line in path.read_text(encoding="utf-8").splitlines()
            if line.strip()
        }

    fresh = [i for i in dict.fromkeys(ids) if i not in existing]
    if fresh:
        with path.open("a", encoding="utf-8") as handle:
            handle.write("\n".join(fresh) + "\n")
    return path
