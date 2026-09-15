import { useJob } from "../hooks";
import { JobStatusBadge } from "./JobStatusBadge";

function JobRow({ jobId, selected, onSelect }: { jobId: string; selected: boolean; onSelect: () => void }) {
  const { data: job } = useJob(jobId);

  return (
    <button
      onClick={onSelect}
      className={`flex w-full items-center justify-between rounded-md border px-3 py-2 text-left text-sm ${
        selected ? "border-indigo-400 bg-indigo-50" : "border-slate-200 bg-white hover:bg-slate-50"
      }`}
    >
      <span className="font-mono text-xs text-slate-500">{jobId.slice(0, 8)}</span>
      {job ? (
        <span className="flex items-center gap-2">
          {job.status === "succeeded" && (
            <span className="text-xs text-slate-500">
              {job.rows_new + job.rows_changed + job.rows_unchanged} rows
              {job.rows_rejected > 0 && `, ${job.rows_rejected} rejected`}
            </span>
          )}
          <JobStatusBadge status={job.status} />
        </span>
      ) : (
        <span className="text-xs text-slate-400">loading…</span>
      )}
    </button>
  );
}

export function JobsList({
  jobIds,
  selectedJobId,
  onSelect,
}: {
  jobIds: string[];
  selectedJobId: string | null;
  onSelect: (jobId: string) => void;
}) {
  if (jobIds.length === 0) {
    return <p className="text-sm text-slate-500">No jobs yet — start one above.</p>;
  }

  return (
    <div className="flex flex-col gap-2">
      {jobIds.map((id) => (
        <JobRow key={id} jobId={id} selected={id === selectedJobId} onSelect={() => onSelect(id)} />
      ))}
    </div>
  );
}
