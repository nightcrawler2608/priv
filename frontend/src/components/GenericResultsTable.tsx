import { useState } from "react";
import { useSiteResults } from "../hooks";
import { siteExportUrl, type SiteDefinition } from "../api";

const PAGE_SIZE = 10;

export function GenericResultsTable({
  site,
  jobId,
  jobSucceeded,
}: {
  site: SiteDefinition;
  jobId: string;
  jobSucceeded: boolean;
}) {
  const [page, setPage] = useState(0);
  const { data, isLoading } = useSiteResults(site.id, jobId, PAGE_SIZE, page * PAGE_SIZE, jobSucceeded);

  if (!jobSucceeded) {
    return <p className="text-sm text-slate-500">Results will appear once the job succeeds.</p>;
  }
  if (isLoading || !data) {
    return <p className="text-sm text-slate-500">Loading results…</p>;
  }

  const totalPages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));
  const columns = site.fields.map((f) => f.name);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex justify-end">
        <a
          href={siteExportUrl(site.id, jobId)}
          className="rounded-md border border-slate-300 px-3 py-1 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Download CSV
        </a>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-max overflow-hidden rounded-md border border-slate-200 text-left text-sm">
          <thead className="bg-slate-50 text-slate-600">
            <tr>
              {columns.map((col) => (
                <th key={col} className="px-3 py-2">{col}</th>
              ))}
            </tr>
          </thead>
          <tbody>
            {data.items.map((item) => (
              <tr key={item.key} className="border-t border-slate-100">
                {columns.map((col) => (
                  <td key={col} className="px-3 py-2">{String(item.data[col] ?? "")}</td>
                ))}
              </tr>
            ))}
            {data.items.length === 0 && (
              <tr>
                <td colSpan={columns.length} className="px-3 py-4 text-center text-slate-400">
                  No rows yet.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      <div className="flex items-center justify-between text-sm text-slate-600">
        <span>
          Page {page + 1} of {totalPages} ({data.total} rows total)
        </span>
        <div className="flex gap-2">
          <button
            onClick={() => setPage((p) => Math.max(0, p - 1))}
            disabled={page === 0}
            className="rounded-md border border-slate-300 px-2 py-1 disabled:opacity-40"
          >
            Prev
          </button>
          <button
            onClick={() => setPage((p) => Math.min(totalPages - 1, p + 1))}
            disabled={page + 1 >= totalPages}
            className="rounded-md border border-slate-300 px-2 py-1 disabled:opacity-40"
          >
            Next
          </button>
        </div>
      </div>
    </div>
  );
}
