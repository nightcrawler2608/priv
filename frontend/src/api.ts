// The frontend never scrapes -- it only calls the FastAPI backend built in
// Phase 4 and renders whatever comes back.
const API_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export type JobStatus = "queued" | "running" | "succeeded" | "failed";

export interface Job {
  id: string;
  status: JobStatus;
  max_pages: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  rows_new: number;
  rows_changed: number;
  rows_unchanged: number;
  rows_rejected: number;
  error_message: string | null;
}

export interface BookRow {
  url: string;
  title: string;
  price: number;
  rating: number;
  availability: string;
  recorded_at: string;
}

export interface PaginatedBooks {
  total: number;
  limit: number;
  offset: number;
  items: BookRow[];
}

async function asJson<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const detail = await res.json().catch(() => ({}));
    throw new Error(detail.detail ?? `request failed: ${res.status}`);
  }
  return res.json() as Promise<T>;
}

export function createJob(maxPages: number): Promise<Job> {
  return fetch(`${API_URL}/jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ max_pages: maxPages }),
  }).then((res) => asJson<Job>(res));
}

export function getJob(jobId: string): Promise<Job> {
  return fetch(`${API_URL}/jobs/${jobId}`).then((res) => asJson<Job>(res));
}

export function getResults(jobId: string, limit: number, offset: number): Promise<PaginatedBooks> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return fetch(`${API_URL}/jobs/${jobId}/results?${params}`).then((res) => asJson<PaginatedBooks>(res));
}

export function exportUrl(jobId: string): string {
  return `${API_URL}/jobs/${jobId}/export`;
}
