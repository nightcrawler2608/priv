import type { JobStatus } from "../api";

const STYLES: Record<JobStatus, string> = {
  queued: "bg-slate-100 text-slate-700",
  running: "bg-amber-100 text-amber-800",
  succeeded: "bg-emerald-100 text-emerald-800",
  failed: "bg-red-100 text-red-800",
};

export function JobStatusBadge({ status }: { status: JobStatus }) {
  return (
    <span className={`rounded-full px-2.5 py-0.5 text-xs font-medium ${STYLES[status]}`}>
      {status}
    </span>
  );
}
