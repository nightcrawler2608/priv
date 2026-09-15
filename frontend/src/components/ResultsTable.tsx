import { useMemo, useState } from "react";
import { useResults } from "../hooks";
import { exportUrl } from "../api";

const PAGE_SIZE = 10;

export function ResultsTable({ jobId, jobSucceeded }: { jobId: string; jobSucceeded: boolean }) {
  const [page, setPage] = useState(0);
  const [availabilityFilter, setAvailabilityFilter] = useState("all");

  const { data, isLoading } = useResults(jobId, PAGE_SIZE, page * PAGE_SIZE, jobSucceeded);

  const filteredItems = useMemo(() => {
    if (!data) return [];
    if (availabilityFilter === "all") return data.items;
    return data.items.filter((row) =>
      availabilityFilter === "in_stock" ? row.availability.toLowerCase().includes("in stock") : !row.availability.toLowerCase().includes("in stock"),
    );
  }, [data, availabilityFilter]);

  if (!jobSucceeded) {
    return <p className="text-sm text-slate-500">Results will appear once the job succeeds.</p>;
  }
  if (isLoading || !data) {
    return <p className="text-sm text-slate-500">Loading results…</p>;
  }

  const totalPages = Math.max(1, Math.ceil(data.total / PAGE_SIZE));

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <select
          value={availabilityFilter}
          onChange={(e) => setAvailabilityFilter(e.target.value)}
          className="rounded-md border border-slate-300 px-2 py-1 text-sm"
        >
          <option value="all">All availability</option>
          <option value="in_stock">In stock only</option>
          <option value="out_of_stock">Out of stock only</option>
        </select>
        <a
          href={exportUrl(jobId)}
          className="rounded-md border border-slate-300 px-3 py-1 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Download CSV
        </a>
      </div>

      <table className="w-full overflow-hidden rounded-md border border-slate-200 text-left text-sm">
        <thead className="bg-slate-50 text-slate-600">
          <tr>
            <th className="px-3 py-2">Title</th>
            <th className="px-3 py-2">Price</th>
            <th className="px-3 py-2">Rating</th>
            <th className="px-3 py-2">Availability</th>
          </tr>
        </thead>
        <tbody>
          {filteredItems.map((row) => (
            <tr key={row.url} className="border-t border-slate-100">
              <td className="px-3 py-2">{row.title}</td>
              <td className="px-3 py-2">£{row.price.toFixed(2)}</td>
              <td className="px-3 py-2">{row.rating}★</td>
              <td className="px-3 py-2">{row.availability}</td>
            </tr>
          ))}
          {filteredItems.length === 0 && (
            <tr>
              <td colSpan={4} className="px-3 py-4 text-center text-slate-400">
                No rows match this filter.
              </td>
            </tr>
          )}
        </tbody>
      </table>

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
