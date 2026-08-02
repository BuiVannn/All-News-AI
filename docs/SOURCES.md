# Khảo sát nguồn — mở rộng cho M4

> Dò thực tế ngày 2026-08-02. Mọi trạng thái dưới đây đến từ việc gọi endpoint
> thật, không phải từ tài liệu. Phương pháp này đã bắt được 5 vấn đề mà tài liệu
> nói sai: arXiv 429, OpenAlex bắt buộc key, `trending_score` trả 400, ngày
> RFC-822, `generateContent` thành legacy.

---

## 1. Kết luận ngắn

| Nhóm | Gom tự động được | Chỉ đọc thủ công |
|---|---|---|
| Paper | HF Daily Papers, arXiv RSS, Semantic Scholar | alphaXiv, OpenReview, emergentmind |
| Model | HF Models/Datasets/Spaces, OpenRouter | LMArena, Artificial Analysis, Replicate |
| Repo | **goodailist API** ⭐, GitHub Search | GitHub Trending (chỉ HTML) |
| Blog lab | 15 feed đã xác nhận | **Anthropic, Meta AI, xAI, DeepSeek, Cohere, Qwen** |
| Newsletter | 13 feed đã xác nhận | — |
| Cộng đồng | HN, Lobsters, (Reddit) | **X/Twitter** |

**Hai chỗ không có đường miễn phí:** X/Twitter và 6 blog lab lớn. Đây là lý do
trang thư mục nguồn tồn tại — thứ không gom được thì gắn link để tự vào đọc.

---

## 2. Phát hiện đắt giá nhất: goodailist API

`GET https://goodailist.com/api/repos` — không công bố nhưng public, không cần auth.

**17.244 repo**, mỗi bản ghi có:

```
repo, description, stars, forks, language, country, archived,
star_1d, star_1d_pct, star_7d, star_7d_pct,     <- tăng trưởng sao
category, subcat, keywords, top_devs,            <- đã phân loại sẵn
is_new, first_seen, created_at, updated_at
```

Vì sao đáng giá hơn GitHub Search:

1. **`star_1d` / `star_7d`** là chính xác tín hiệu `github_stars_delta` mà
   `config/weights.yaml` đã có trọng số 4.0 nhưng **chưa nguồn nào cấp**. Tốc độ
   tăng sao phân biệt được repo đang bùng nổ với repo cũ nhiều sao.
2. **`category` / `subcat`** cho phân loại sẵn, đỡ phải đoán chủ đề bằng từ khoá.
3. **`is_new` / `first_seen`** để phát hiện repo mới nổi.
4. GitHub Search API không trả bất kỳ thứ nào ở trên và giới hạn 30 req/phút.

**Cảnh báo kỹ thuật:** response là **9.4 MB** cho toàn bộ 17k repo, không thấy
tham số lọc. Phải tải hết rồi lọc phía mình. Ở tần suất 2 lần/ngày thì chấp nhận
được, nhưng cần đặt timeout rộng và cân nhắc cache theo `ETag`.

**Rủi ro:** API không công bố nên không có cam kết ổn định. Phải coi như nguồn
có thể biến mất bất cứ lúc nào — đúng như mọi nguồn khác, collector đã cô lập lỗi.

---

## 3. X/Twitter — không có đường miễn phí

| Phương án | Chi phí | Đánh giá |
|---|---|---|
| X API chính thức | **Đã bỏ free tier từ 02/2026.** Pay-per-use $0.005/post đọc, trần 2 triệu/tháng | ~$30/tháng ở 200 post/ngày |
| Legacy Basic | $200/tháng | Đã đóng đăng ký mới |
| Bên thứ ba (TwitterAPI.io, GetXAPI) | $0.05–0.15 / 1.000 tweet | ~$0,30–0,90/tháng nhưng là scraper, vi phạm ToS của X, dễ chết |
| RSSHub public | Miễn phí | **rsshub.app trả 403** — chặn IP datacenter. Self-host thì cần server, phá vỡ kiến trúc không-server |
| Nitter | Miễn phí | Gần như đã chết từ 2024 |

**Khuyến nghị: không tích hợp X.** Ba lý do:

1. Không có đường vừa miễn phí vừa hợp lệ.
2. **Nội dung X gần như luôn được phản chiếu.** Thông báo lớn của lab đều xuất
   hiện trên HN, Reddit hoặc chính blog của lab trong vài giờ. Giá trị biên của
   X là "sớm hơn vài tiếng", không phải "nội dung độc quyền".
3. Scraper bên thứ ba đưa rủi ro pháp lý và vận hành vào một dự án cá nhân
   đang có chi phí bằng 0.

**Thay thế:** đưa X vào **trang thư mục** — link tới danh sách account và X List
đáng theo dõi, để bạn chủ động vào đọc. Đó chính là thứ bạn đã yêu cầu.

---

## 4. Blog lab không có RSS

Đã dò autodiscovery (`<link rel="alternate" type="application/rss+xml">`) trên
trang chủ, không chỉ đoán đường dẫn:

**Không có feed:** Anthropic, Meta AI (`ai.meta.com`), xAI, DeepSeek, Cohere,
Qwen, Runway, Perplexity.

**Tìm thêm được nhờ autodiscovery** (mà đoán đường dẫn đã bỏ sót ở M1):

| Lab | Feed | Bài mới nhất |
|---|---|---|
| Mistral | `https://mistral.ai/rss.xml` | 23 ngày |
| Allen AI | `https://allenai.org/rss.xml` | 2 ngày |
| Stability | `https://stability.ai/news-updates?format=rss` | 73 ngày |
| Google AI | `https://blog.google/technology/ai/rss/` | mới |
| Apple ML | `https://machinelearning.apple.com/rss.xml` | mới |
| Meta Engineering | `https://engineering.fb.com/feed/` | mới |
| EleutherAI | `https://blog.eleuther.ai/index.xml` | mới |
| Together AI | `https://www.together.ai/blog/rss.xml` | mới |

**Với 6 lab không có feed**, các lựa chọn và vì sao đều bị loại:

- *Crawl HTML trực tiếp*: phá vỡ nguyên tắc "chỉ API chính thức và RSS", cần
  headless browser trong CI, và các site này đều là Next.js render động.
- *Change detection*: thêm hạ tầng, vẫn phải parse HTML.
- *RSSHub self-host*: cần server chạy 24/7.

→ **Phủ gián tiếp qua Hacker News và Reddit.** Thông báo của Anthropic/Meta/xAI
gần như luôn lên HN trong vài giờ. Cộng thêm link trực tiếp ở trang thư mục.

---

## 5. Nguồn đã xác nhận hoạt động (2026-08-02)

### Newsletter — nhóm giá trị cao nhất chưa khai thác

Đây là nội dung **đã qua tay người biên tập**, tín hiệu sạch hơn nhiều so với
feed thô. Tất cả đều RSS công khai, miễn phí.

| Tên | Feed | Ghi chú |
|---|---|---|
| Import AI (Jack Clark) | `importai.substack.com/feed` | Phân tích chính sách + kỹ thuật |
| Interconnects (Nathan Lambert) | `interconnects.ai/feed` | Sâu về post-training, RLHF |
| Last Week in AI | `lastweekin.ai/feed` | Tổng hợp tuần |
| AI News (smol.ai) | `news.smol.ai/rss.xml` | Tổng hợp Discord/Twitter/Reddit hằng ngày |
| TLDR AI | `tldr.tech/api/rss/ai` | Ngắn, hằng ngày |
| Simon Willison | `simonwillison.net/atom/everything/` | Thực dụng, thử nghiệm thật |
| Sebastian Raschka | `magazine.sebastianraschka.com/feed` | Giải thích kỹ thuật |
| The Sequence | `thesequence.substack.com/feed` | |
| Latent Space | `latent.space/feed` | Podcast + bài viết kỹ sư AI |
| AI Weekly | `aiweekly.co/issues.rss` | |
| ChinAI (Jeff Ding) | `chinai.substack.com/feed` | AI Trung Quốc, dịch nguồn gốc |
| AI Supremacy | `ai-supremacy.com/feed` | |
| Oxen ArXiv Dives | `ghost.oxen.ai/rss/` | Mổ xẻ paper |

**`news.smol.ai` đặc biệt đáng chú ý**: nó đã làm sẵn việc tổng hợp Discord,
Twitter và Reddit — tức là phủ gián tiếp được đúng phần X mà ta không lấy được.

### Cộng đồng

| Nguồn | Endpoint | Trạng thái |
|---|---|---|
| HN Algolia | `hn.algolia.com/api/v1/search` | ✅ miễn phí, không key |
| HN Firebase | `hacker-news.firebaseio.com/v0/topstories.json` | ✅ |
| Lobsters | `lobste.rs/t/ai.json` | ✅ |
| Reddit | `reddit.com/r/{sub}/.rss` | ⚠️ **chưa kiểm chứng được** — sandbox này chặn `reddit.com` ở tầng mạng (curl trả `000`). `oauth.reddit.com` vẫn resolve (403 vì thiếu auth). Nhiều khả năng chạy được trong GitHub Actions; phải thử ở đó |

### Model / dataset / space

`huggingface.co/api/{models,datasets,spaces}?sort=trendingScore` — cả ba đều
chạy. Datasets và Spaces là hai loại nội dung hoàn toàn chưa khai thác.

### Cần API key (chưa dùng)

Artificial Analysis (401), Replicate (401), LMArena (403), OpenReview (403).

---

## 6. Kế hoạch M4

Xếp theo **giá trị / công sức**, không theo thứ tự thích:

| Ưu tiên | Nguồn | Vì sao | Công sức |
|---|---|---|---|
| **1** | goodailist API | Mở khoá `kind=repo` + cấp `star_1d` cho scoring | Thấp — một collector |
| **2** | 13 newsletter RSS | Nội dung đã curate, tín hiệu sạch nhất. Dùng lại `BlogsRSSCollector` | Rất thấp — thêm vào config |
| **3** | 8 blog lab mới | Lấp chỗ trống Mistral/AllenAI/Google/Apple | Rất thấp — thêm vào config |
| **4** | Hacker News | Cấp `hn_points`, phủ gián tiếp X và các lab không RSS | Thấp |
| **5** | Reddit | Cấp `reddit_score`, cộng đồng LocalLLaMA rất nhanh | Trung bình — phải xử lý auth, chưa test được từ đây |
| **6** | HF Datasets + Spaces | Hai loại nội dung mới | Thấp |
| **7** | MCP Registry | `kind=tool`, mảng chưa ai làm | Thấp |
| — | X/Twitter | Không có đường miễn phí hợp lệ | **Không làm** |

Ưu tiên 2 và 3 gần như miễn phí về công sức: `BlogsRSSCollector` đã viết xong,
chỉ cần thêm dòng vào `config/sources.yaml`.

**Cần điều chỉnh kèm theo:** thêm 13 newsletter + 8 blog sẽ làm `kind=release`
phình lên. Phải chỉnh lại hạn ngạch trong `feed.quotas`, và có thể cần tách
`newsletter` thành một `kind` riêng.

---

## 7. Việc không nên làm

**Không tích hợp tool crawl.** Bạn có nhắc tới chuyện này. Lý do từ chối:

- Phá vỡ nguyên tắc "chỉ API chính thức và RSS" đang giữ dự án sạch về pháp lý.
- Cần headless browser (Playwright) trong CI — chậm, nặng, hay hỏng.
- Các site cần crawl nhất (Anthropic, X, Meta) đều có chống bot mạnh nhất.
- Chi phí bảo trì cao: mỗi lần site đổi HTML là hỏng, mà hỏng thầm lặng.

Đổi lại, ba cơ chế phủ được phần lớn khoảng trống mà crawl nhắm tới: newsletter
đã curate, Hacker News, và trang thư mục nguồn để tự đọc.
