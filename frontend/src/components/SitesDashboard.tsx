import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createSiteJob } from "../api";
import { useJob, useSites } from "../hooks";
import { QuickAddSite } from "./QuickAddSite";
import { SiteForm } from "./SiteForm";
import { SitesList } from "./SitesList";
import { GenericResultsTable } from "./GenericResultsTable";
import { JobStatusBadge } from "./JobStatusBadge";
import { JobRowsChart } from "./JobRowsChart";

export function SitesDashboard() {
  const [showManualForm, setShowManualForm] = useState(false);
  const [selectedSiteId, setSelectedSiteId] = useState<string | null>(null);
  const [jobId, setJobId] = useState<string | null>(null);

  const { data: sites } = useSites();
  const { data: job } = useJob(jobId);
  const queryClient = useQueryClient();

  const startJob = useMutation({
    mutationFn: () => createSiteJob(selectedSiteId as string),
    onSuccess: (newJob) => setJobId(newJob.id),
  });

  const selectedSite = sites?.find((s) => s.id === selectedSiteId) ?? null;

  function handleSiteCreated(siteId: string) {
    setSelectedSiteId(siteId);
    setJobId(null);
    queryClient.invalidateQueries({ queryKey: ["sites"] });
  }

  return (
    <div className="flex flex-col gap-4">
      <QuickAddSite onCreated={handleSiteCreated} />

      <div>
        <button
          onClick={() => setShowManualForm((v) => !v)}
          className="text-xs font-medium text-slate-500 hover:text-slate-700 hover:underline"
        >
          {showManualForm ? "Hide manual setup" : "Advanced: enter CSS selectors manually"}
        </button>
        {showManualForm && (
          <div className="mt-2">
            <SiteForm onCreated={handleSiteCreated} />
          </div>
        )}
      </div>

      <section className="grid grid-cols-1 gap-6 md:grid-cols-[240px_1fr]">
        <div>
          <h2 className="mb-2 text-sm font-semibold text-slate-700">Sites</h2>
          <SitesList
            selectedSiteId={selectedSiteId}
            onSelect={(siteId) => {
              setSelectedSiteId(siteId);
              setJobId(null);
            }}
          />
        </div>

        <div className="flex flex-col gap-4">
          {selectedSite === null ? (
            <p className="text-sm text-slate-500">Select a site to run it.</p>
          ) : (
            <>
              <div className="flex items-center gap-3">
                <button
                  onClick={() => startJob.mutate()}
                  disabled={startJob.isPending}
                  className="rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
                >
                  {startJob.isPending ? "Starting…" : `Run "${selectedSite.name}"`}
                </button>
                {job && <JobStatusBadge status={job.status} />}
              </div>

              {job?.status === "failed" && (
                <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">Job failed: {job.error_message}</p>
              )}
              {job?.status === "succeeded" && <JobRowsChart job={job} />}
              {jobId && (
                <GenericResultsTable site={selectedSite} jobId={jobId} jobSucceeded={job?.status === "succeeded"} />
              )}
            </>
          )}
        </div>
      </section>
    </div>
  );
}
