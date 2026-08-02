/**
 * Thư mục nguồn tin AI, phân theo mục đích sử dụng.
 *
 * `ingested: true` = ai-radar đã tự gom, không cần vào đọc thủ công.
 * `ingested: false` = phải tự vào đọc, vì không có API/RSS miễn phí hoặc vì
 * nội dung không hợp để gom tự động (bảng xếp hạng, công cụ tra cứu).
 *
 * Lý do từng nguồn nằm ở nhóm nào: docs/SOURCES.md
 */

export interface Source {
  name: string;
  url: string;
  note: string;
  /** ai-radar đã gom tự động chưa. */
  ingested?: boolean;
}

export interface Section {
  id: string;
  title: string;
  intro: string;
  sources: Source[];
}

export const DIRECTORY: Section[] = [
  {
    id: "hang-ngay",
    title: "Đọc hằng ngày",
    intro:
      "Nơi tin mới xuất hiện trước tiên. Nếu chỉ có 10 phút mỗi ngày thì đọc nhóm này.",
    sources: [
      {
        name: "AI News (smol.ai)",
        url: "https://news.smol.ai/",
        note: "Tổng hợp Discord, X và Reddit mỗi ngày. Phủ gián tiếp đúng phần X mà ai-radar không lấy được.",
        ingested: true,
      },
      {
        name: "Hacker News — AI",
        url: "https://hn.algolia.com/?query=LLM&sort=byPopularity&type=story",
        note: "Thông báo lớn của lab gần như luôn lên đây trong vài giờ, kể cả các lab không có RSS.",
      },
      {
        name: "r/LocalLLaMA",
        url: "https://www.reddit.com/r/LocalLLaMA/",
        note: "Cộng đồng phản ứng nhanh nhất với model mở. Benchmark thực tế và lỗi thật.",
      },
      {
        name: "TLDR AI",
        url: "https://tldr.tech/ai",
        note: "Bản tin ngắn hằng ngày, đọc hết trong 3 phút.",
        ingested: true,
      },
      {
        name: "Hugging Face Daily Papers",
        url: "https://huggingface.co/papers",
        note: "Paper được cộng đồng vote mỗi ngày. Nguồn curate tốt nhất cho paper.",
        ingested: true,
      },
    ],
  },
  {
    id: "mang-xa-hoi",
    title: "Mạng xã hội",
    intro:
      "ai-radar KHÔNG gom được nhóm này: X đã bỏ free tier từ 02/2026 và chuyển sang tính tiền theo lượt đọc. Đây là chỗ bạn phải tự vào.",
    sources: [
      {
        name: "X — danh sách AI research",
        url: "https://x.com/i/lists/1600848466382381057",
        note: "X List gom sẵn các nhà nghiên cứu hàng đầu. Đọc list đỡ nhiễu hơn nhiều so với dòng thời gian.",
      },
      {
        name: "X — @_akhaliq",
        url: "https://x.com/_akhaliq",
        note: "Đăng paper mới liên tục, thường sớm hơn mọi nơi khác.",
      },
      {
        name: "X — @simonw",
        url: "https://x.com/simonw",
        note: "Thử nghiệm thật, ghi chép thẳng thắn về cái gì chạy và cái gì không.",
      },
      {
        name: "r/MachineLearning",
        url: "https://www.reddit.com/r/MachineLearning/",
        note: "Thiên về nghiên cứu, ít tin đồn hơn r/LocalLLaMA.",
      },
      {
        name: "Lobsters — AI",
        url: "https://lobste.rs/t/ai",
        note: "Nhỏ hơn HN, tỷ lệ nhiễu thấp hơn.",
      },
      {
        name: "Hugging Face Posts",
        url: "https://huggingface.co/posts",
        note: "Tác giả model tự thông báo, thường kèm chi tiết kỹ thuật.",
      },
    ],
  },
  {
    id: "paper",
    title: "Tìm paper",
    intro: "Ngoài arXiv và HF mà ai-radar đã gom, đây là các công cụ tra cứu sâu.",
    sources: [
      {
        name: "arXiv — cs.CL / cs.LG / cs.CV",
        url: "https://arxiv.org/list/cs.CL/recent",
        note: "Nguồn gốc. ai-radar lấy qua RSS vì Query API bị siết rate limit từ 02/2026.",
        ingested: true,
      },
      {
        name: "alphaXiv",
        url: "https://www.alphaxiv.org/",
        note: "Thảo luận trên từng paper arXiv. Không có API mở nên phải tự vào.",
      },
      {
        name: "Semantic Scholar",
        url: "https://www.semanticscholar.org/",
        note: "Tra citation, tác giả, paper liên quan. Có API miễn phí.",
      },
      {
        name: "Connected Papers",
        url: "https://www.connectedpapers.com/",
        note: "Vẽ đồ thị paper liên quan — hữu ích khi mới vào một mảng lạ.",
      },
      {
        name: "Emergent Mind",
        url: "https://www.emergentmind.com/",
        note: "Xếp hạng paper theo độ thảo luận trên mạng xã hội.",
      },
      {
        name: "OpenReview",
        url: "https://openreview.net/",
        note: "Bản review của ICLR, NeurIPS. Đọc phần phản biện thường giá trị hơn chính paper.",
      },
      {
        name: "Papers with Code (lưu trữ)",
        url: "https://github.com/paperswithcode/paperswithcode-data",
        note: "Đã đóng cửa 24/07/2025. Dữ liệu cũ vẫn còn trên GitHub.",
      },
    ],
  },
  {
    id: "model",
    title: "Model & bảng xếp hạng",
    intro: "So sánh năng lực, giá và tốc độ trước khi chọn model.",
    sources: [
      {
        name: "Hugging Face — Trending",
        url: "https://huggingface.co/models?sort=trending",
        note: "Model mở mới ra. ai-radar lọc bỏ bản lượng tử hoá để không bị biến thể chiếm chỗ.",
        ingested: true,
      },
      {
        name: "OpenRouter — Models",
        url: "https://openrouter.ai/models",
        note: "Bắt cả model đóng, kèm giá và context length. Có API công khai.",
      },
      {
        name: "LMArena",
        url: "https://lmarena.ai/leaderboard",
        note: "Xếp hạng theo bình chọn người dùng thật. Không có API mở.",
      },
      {
        name: "Artificial Analysis",
        url: "https://artificialanalysis.ai/",
        note: "So sánh chất lượng / giá / tốc độ. API cần key.",
      },
      {
        name: "Ollama Library",
        url: "https://ollama.com/library",
        note: "Model chạy được tại máy. Chỉ có HTML, không API.",
      },
      {
        name: "Hugging Face Spaces",
        url: "https://huggingface.co/spaces?sort=trending",
        note: "Demo chạy thử ngay trên web, không cần cài.",
      },
    ],
  },
  {
    id: "code",
    title: "Code & repo",
    intro: "Thư viện, framework và công cụ mới nổi.",
    sources: [
      {
        name: "GoodAIList — Repos",
        url: "https://goodailist.com/repos",
        note: "17.000 repo AI kèm tốc độ tăng sao theo ngày/tuần và phân loại sẵn. Có API công khai.",
      },
      {
        name: "GitHub Trending",
        url: "https://github.com/trending?since=daily",
        note: "Chỉ có HTML, không API chính thức.",
      },
      {
        name: "MCP Registry",
        url: "https://registry.modelcontextprotocol.io/",
        note: "Đăng ký MCP server chính thức. Mảng gần như chưa ai tổng hợp.",
      },
      {
        name: "Awesome MCP Servers",
        url: "https://github.com/punkpeye/awesome-mcp-servers",
        note: "Danh sách do cộng đồng duy trì, cập nhật nhanh hơn registry chính thức.",
      },
    ],
  },
  {
    id: "lab",
    title: "Blog chính thức của lab",
    intro:
      "Nguồn gốc của mọi thông báo. Sáu lab đầu KHÔNG có RSS nên ai-radar không gom được — phải tự vào hoặc bắt gián tiếp qua Hacker News.",
    sources: [
      { name: "Anthropic", url: "https://www.anthropic.com/news", note: "Không có RSS." },
      { name: "Meta AI", url: "https://ai.meta.com/blog/", note: "Không có RSS." },
      { name: "xAI", url: "https://x.ai/news", note: "Không có RSS." },
      { name: "DeepSeek", url: "https://api-docs.deepseek.com/news/", note: "Không có RSS." },
      { name: "Qwen", url: "https://qwen.ai/blog", note: "Không có RSS; feed cũ đã ngừng cập nhật 313 ngày." },
      { name: "Cohere", url: "https://cohere.com/blog", note: "Không có RSS." },
      { name: "OpenAI", url: "https://openai.com/news/", note: "", ingested: true },
      { name: "Google DeepMind", url: "https://deepmind.google/discover/blog/", note: "", ingested: true },
      { name: "Google AI", url: "https://blog.google/technology/ai/", note: "", ingested: true },
      { name: "Mistral", url: "https://mistral.ai/news", note: "", ingested: true },
      { name: "Allen AI", url: "https://allenai.org/blog", note: "", ingested: true },
      { name: "Apple ML", url: "https://machinelearning.apple.com/", note: "", ingested: true },
      { name: "NVIDIA Developer", url: "https://developer.nvidia.com/blog/", note: "", ingested: true },
      { name: "Microsoft Research", url: "https://www.microsoft.com/en-us/research/blog/", note: "", ingested: true },
      { name: "Hugging Face", url: "https://huggingface.co/blog", note: "", ingested: true },
      { name: "EleutherAI", url: "https://blog.eleuther.ai/", note: "", ingested: true },
      { name: "Together AI", url: "https://www.together.ai/blog", note: "", ingested: true },
      { name: "BAIR (Berkeley)", url: "https://bair.berkeley.edu/blog/", note: "", ingested: true },
    ],
  },
  {
    id: "newsletter",
    title: "Newsletter",
    intro:
      "Nội dung đã qua tay người biên tập — tín hiệu sạch hơn nhiều so với feed thô. Đây là nhóm ai-radar khai thác mạnh nhất.",
    sources: [
      {
        name: "Import AI — Jack Clark",
        url: "https://importai.substack.com/",
        note: "Giao giữa kỹ thuật và chính sách. Viết bởi người trong cuộc.",
        ingested: true,
      },
      {
        name: "Interconnects — Nathan Lambert",
        url: "https://www.interconnects.ai/",
        note: "Sâu về post-training, RLHF, model mở.",
        ingested: true,
      },
      {
        name: "Simon Willison",
        url: "https://simonwillison.net/",
        note: "Thực dụng nhất: thử thật rồi mới viết.",
        ingested: true,
      },
      {
        name: "Sebastian Raschka",
        url: "https://magazine.sebastianraschka.com/",
        note: "Giải thích kỹ thuật từ gốc, hợp với người mới.",
        ingested: true,
      },
      {
        name: "Latent Space",
        url: "https://www.latent.space/",
        note: "Podcast và bài viết cho kỹ sư AI.",
        ingested: true,
      },
      {
        name: "Last Week in AI",
        url: "https://lastweekin.ai/",
        note: "Tổng hợp tuần, đỡ bỏ sót.",
        ingested: true,
      },
      {
        name: "The Sequence",
        url: "https://thesequence.substack.com/",
        note: "",
        ingested: true,
      },
      {
        name: "ChinAI — Jeff Ding",
        url: "https://chinai.substack.com/",
        note: "Dịch nguồn gốc tiếng Trung. Mảng gần như không có ở đâu khác.",
        ingested: true,
      },
      {
        name: "Oxen — ArXiv Dives",
        url: "https://ghost.oxen.ai/",
        note: "Mổ xẻ từng paper một cách chi tiết.",
        ingested: true,
      },
      {
        name: "The Batch — Andrew Ng",
        url: "https://www.deeplearning.ai/the-batch/",
        note: "Không tìm được RSS còn hoạt động.",
      },
    ],
  },
  {
    id: "hoc",
    title: "Học & tra cứu",
    intro: "Không phải tin tức, nhưng là chỗ quay lại khi cần hiểu sâu một khái niệm.",
    sources: [
      {
        name: "Hugging Face Docs",
        url: "https://huggingface.co/docs",
        note: "Tài liệu transformers, datasets, diffusers.",
      },
      {
        name: "The Illustrated Transformer",
        url: "https://jalammar.github.io/illustrated-transformer/",
        note: "Bài giải thích transformer bằng hình, vẫn là bản tốt nhất.",
      },
      {
        name: "Lil'Log — Lilian Weng",
        url: "https://lilianweng.github.io/",
        note: "Bài tổng quan dài, chất lượng cao về agent, RL, diffusion.",
      },
      {
        name: "Anthropic — Building Effective Agents",
        url: "https://www.anthropic.com/engineering/building-effective-agents",
        note: "Hướng dẫn thiết kế agent, thực dụng và ngắn.",
      },
      {
        name: "Model Context Protocol",
        url: "https://modelcontextprotocol.io/",
        note: "Tài liệu gốc của MCP.",
      },
    ],
  },
];
