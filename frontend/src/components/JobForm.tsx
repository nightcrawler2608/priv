import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createJob } from "../api";

export function JobForm({ onCreated }: { onCreated: (jobId: string) => void }) {
  const [maxPages, setMaxPages] = useState(1);
  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () => createJob(maxPages),
    onSuccess: (job) => {
      queryClient.invalidateQueries({ queryKey: ["job", job.id] });
      onCreated(job.id);
    },
  });

  return (
    <form
      className="flex items-end gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
      onSubmit={(e) => {
        e.preventDefault();
        mutation.mutate();
      }}
    >
      <div className="flex flex-col gap-1">
        <label htmlFor="max_pages" className="text-sm font-medium text-slate-700">
          Catalogue pages to scrape
        </label>
        <input
          id="max_pages"
          type="number"
          min={1}
          max={50}
          value={maxPages}
          onChange={(e) => setMaxPages(Number(e.target.value))}
          className="w-32 rounded-md border border-slate-300 px-2 py-1.5 text-sm"
        />
      </div>
      <button
        type="submit"
        disabled={mutation.isPending}
        className="rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
      >
        {mutation.isPending ? "Starting…" : "Start scrape job"}
      </button>
      {mutation.isError && (
        <p className="text-sm text-red-600">{(mutation.error as Error).message}</p>
      )}
    </form>
  );
}
