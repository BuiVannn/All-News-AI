/**
 * Đọc data/items/*.json tại thời điểm build.
 *
 * Không có API, không có database — web chỉ là bản render tĩnh của những file
 * JSON mà pipeline Python đã ghi ra. Đổi lại: không có gì để sập, và mỗi bản
 * deploy tương ứng chính xác với một commit trong git.
 */
import fs from "node:fs";
import path from "node:path";

const DATA_DIR = path.resolve(process.cwd(), "..", "data", "items");

export interface Link {
  source: string;
  url: string;
  external_id: string | null;
}

export interface Signals {
  hf_upvotes: number;
  hf_likes: number;
  hf_downloads: number;
  github_stars: number;
  has_code: boolean;
  has_weights: boolean;
}

export interface Item {
  id: string;
  kind: "paper" | "model" | "release" | "repo" | "tool";
  title: string;
  summary_en: string | null;
  summary_vi: string | null;
  why_it_matters: string | null;
  topics: string[];
  links: Link[];
  actors: string[];
  published_at: string;
  signals: Signals;
  score: number;
}

/** Ngày có dữ liệu, mới nhất trước. */
export function listDays(): string[] {
  if (!fs.existsSync(DATA_DIR)) return [];
  return fs
    .readdirSync(DATA_DIR)
    .filter((name) => name.endsWith(".json"))
    .map((name) => name.replace(/\.json$/, ""))
    .sort()
    .reverse();
}

export function loadDay(day: string): Item[] {
  const file = path.join(DATA_DIR, `${day}.json`);
  if (!fs.existsSync(file)) return [];
  return JSON.parse(fs.readFileSync(file, "utf-8")) as Item[];
}

export const KIND_LABEL: Record<Item["kind"], string> = {
  paper: "Paper",
  model: "Model",
  release: "Tin ra mắt",
  repo: "Repo",
  tool: "Tooling",
};

/** Nhãn nguồn cho dễ đọc — `hf_base_model:quantized` thành "model gốc". */
export function linkLabel(link: Link): string {
  if (link.source.startsWith("hf_base_model")) return "model gốc";
  return (
    {
      arxiv: "arXiv",
      hf_papers: "HF Papers",
      hf_models: "Hugging Face",
      github: "GitHub",
      doi: "DOI",
    }[link.source] ?? link.source
  );
}

/** Ghép đường dẫn nội bộ với `base` — cần cho GitHub Pages ở đường dẫn con. */
export function href(pathname: string): string {
  const base = import.meta.env.BASE_URL || "/";
  const prefix = base.endsWith("/") ? base : `${base}/`;
  return prefix + pathname.replace(/^\//, "");
}

export function formatDay(day: string): string {
  const [y, m, d] = day.split("-");
  return `${d}/${m}/${y}`;
}
