// @ts-check
import { defineConfig } from "astro/config";

// GitHub Pages phục vụ site ở /<tên-repo>/ chứ không phải gốc domain, nên
// `base` phải lấy từ env: để trống khi chạy local, đặt trong workflow khi deploy.
// Thiếu bước này thì mọi link nội bộ đều 404 trên Pages.
export default defineConfig({
  site: process.env.ASTRO_SITE ?? "http://localhost:4321",
  base: process.env.ASTRO_BASE ?? "/",
  output: "static",
  // Trang tĩnh thuần: không JS phía client, không gọi API lúc chạy. Toàn bộ dữ
  // liệu đọc từ ../data/items/*.json tại thời điểm build.
  build: { format: "directory" },
});
