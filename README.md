# ai-radar

Gom **paper, model release, tin ra mắt và tooling AI** về một feed duy nhất mỗi ngày — có lọc, có gộp trùng giữa các nguồn, và tóm tắt tiếng Việt.

Mỗi ngày có hàng trăm paper và model mới ra. Vấn đề không phải là tìm chúng ở đâu, mà là **lọc ra 30 thứ đáng đọc** và gom các mảnh rời rạc của cùng một sự kiện lại với nhau.

> 🚧 Đang phát triển — hiện ở mốc M0 (một nguồn, pipeline chạy được đầu-cuối).

## Điểm khác biệt

Cùng một sự kiện thường xuất hiện ở 5 nơi: paper trên arXiv, model trên Hugging Face, repo trên GitHub, bài blog của lab, và post trên Reddit. Các công cụ hiện có hiển thị chúng thành 5 dòng riêng biệt. `ai-radar` gộp thành **một mục có 5 đường dẫn**.

## Kiến trúc

```mermaid
flowchart LR
    A[GitHub Actions<br/>cron 2x/ngày] --> B[Collectors]
    B --> C[Normalize<br/>→ Item]
    C --> D[Dedup +<br/>cross-source link]
    D --> E{Tier-1<br/>rule-based}
    E -->|top 30| F[Tier-2<br/>Claude Haiku]
    E -->|còn lại| G[seen ledger]
    F --> H[data/items/*.json]
    H --> I[Astro static]
    I --> J[Cloudflare Pages]
```

Không có server, không có database. Dữ liệu là file JSON trong git — nghĩa là pipeline **replay được** (chạy lại thuật toán xếp hạng trên toàn bộ lịch sử mà không cần fetch lại), debug bằng `cat`, và rollback bằng `git revert`.

Lý do đằng sau từng quyết định: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).

## Nguồn dữ liệu

| Nguồn | Loại | Trạng thái |
|---|---|---|
| HF Daily Papers | paper | ✅ M0 |
| arXiv RSS | paper | M1 |
| HF Models | model | M1 |
| Blog RSS các lab | tin ra mắt | M1 |
| OpenRouter Models | model closed-source | M4 |
| GitHub Search | repo | M4 |
| MCP Registry | tooling | M4 |
| Hacker News / Reddit | tín hiệu độ nóng | M4 |

Chỉ dùng API chính thức và RSS — không scrape.

> **Ghi chú về arXiv:** dự án cố tình chỉ dùng **RSS** (`rss.arxiv.org`), không dùng Query API. Từ 02/2026, Query API trả HTTP 429 liên tục kể cả khi tuân thủ đúng giới hạn 1 request/3 giây, và đến giữa 06/2026 vẫn chưa có giải pháp. RSS chỉ tốn 5 request/ngày và đã chứa đủ title, abstract, tác giả, DOI.

## Chạy thử

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

python -m ai_radar --date 2026-07-31 --dry-run   # không ghi gì
python -m ai_radar                                # thu thập hôm nay
```

```
2026-07-31  fetched=26  new=26  duplicates=0
  [ok ] hf_papers       0.42s  26 item
```

## Phát triển

```bash
pytest        # test chạy offline, dùng response HTTP đã ghi lại
ruff check .
mypy
```

Thêm một nguồn mới = viết một class kế thừa `Collector` rồi đăng ký vào `collectors/REGISTRY`. Không cần đụng vào pipeline.

## Lộ trình

- [x] **M0** — schema, `Collector` base, HF Daily Papers, ghi JSON
- [ ] **M1** — arXiv RSS + HF Models + blog RSS, dedup chéo nguồn, tier-1 scoring
- [ ] **M2** — tóm tắt tiếng Việt (Claude Haiku), web Astro, deploy
- [ ] **M3** — cron GitHub Actions, run manifest, xử lý lỗi
- [ ] **M4** — thêm GitHub, MCP Registry, OpenRouter, HN, Reddit
- [ ] **M5** — CI, ADR, hoàn thiện tài liệu

## Giấy phép

MIT. Nội dung hiển thị thuộc về nguồn gốc — dự án chỉ hiển thị tiêu đề, đường dẫn và tóm tắt tự sinh, không sao chép lại nội dung gốc.
