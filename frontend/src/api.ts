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

// ---- Config-driven sites: "paste a URL + CSS selectors" instead of a
// hardcoded scraper per site. ----

export type FieldType = "text" | "number";
export type FieldAttr = "text" | "href" | "src" | "title" | "alt";

export interface FieldConfig {
  name: string;
  selector: string;
  attr: string; // "text" or an HTML attribute name
  type: FieldType;
  required: boolean;
}

export interface SiteDefinition {
  id: string;
  name: string;
  base_url: string;
  list_url_template: string;
  item_selector: string;
  key_selector: string | null;
  key_attr: string;
  fields: FieldConfig[];
  max_pages: number;
  created_at: string;
}

export interface SiteCreate {
  name: string;
  base_url: string;
  list_url_template: string;
  item_selector: string;
  key_selector: string | null;
  key_attr: string;
  fields: FieldConfig[];
  max_pages: number;
}

export interface ItemRow {
  key: string;
  data: Record<string, unknown>;
  recorded_at: string;
}

export interface PaginatedItems {
  total: number;
  limit: number;
  offset: number;
  items: ItemRow[];
}

export function createSite(payload: SiteCreate): Promise<SiteDefinition> {
  return fetch(`${API_URL}/sites`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then((res) => asJson<SiteDefinition>(res));
}

export function listSites(): Promise<SiteDefinition[]> {
  return fetch(`${API_URL}/sites`).then((res) => asJson<SiteDefinition[]>(res));
}

export function createSiteJob(siteId: string): Promise<Job> {
  return fetch(`${API_URL}/sites/${siteId}/jobs`, { method: "POST" }).then((res) => asJson<Job>(res));
}

export function getSiteResults(siteId: string, jobId: string, limit: number, offset: number): Promise<PaginatedItems> {
  const params = new URLSearchParams({ limit: String(limit), offset: String(offset) });
  return fetch(`${API_URL}/sites/${siteId}/jobs/${jobId}/results?${params}`).then((res) => asJson<PaginatedItems>(res));
}

export function siteExportUrl(siteId: string, jobId: string): string {
  return `${API_URL}/sites/${siteId}/jobs/${jobId}/export`;
}
