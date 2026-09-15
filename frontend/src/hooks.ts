import { useQuery } from "@tanstack/react-query";
import { getJob, getResults, getSiteResults, listSites } from "./api";

const ACTIVE_STATUSES = new Set(["queued", "running"]);

// Poll every 2s while the job is still queued/running; stop polling once it
// resolves to succeeded/failed. This is the async job pattern from the
// spec: the frontend never blocks on a scrape, it just checks back.
export function useJob(jobId: string | null) {
  return useQuery({
    queryKey: ["job", jobId],
    queryFn: () => getJob(jobId as string),
    enabled: jobId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status && ACTIVE_STATUSES.has(status) ? 2000 : false;
    },
  });
}

export function useResults(jobId: string | null, limit: number, offset: number, enabled: boolean) {
  return useQuery({
    queryKey: ["results", jobId, limit, offset],
    queryFn: () => getResults(jobId as string, limit, offset),
    enabled: jobId !== null && enabled,
  });
}

export function useSites() {
  return useQuery({ queryKey: ["sites"], queryFn: listSites });
}

export function useSiteResults(
  siteId: string | null,
  jobId: string | null,
  limit: number,
  offset: number,
  enabled: boolean,
) {
  return useQuery({
    queryKey: ["site-results", siteId, jobId, limit, offset],
    queryFn: () => getSiteResults(siteId as string, jobId as string, limit, offset),
    enabled: siteId !== null && jobId !== null && enabled,
  });
}
