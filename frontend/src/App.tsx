import { useState } from "react";
import { useJob } from "./hooks";
import { JobForm } from "./components/JobForm";
import { JobsList } from "./components/JobsList";
import { ResultsTable } from "./components/ResultsTable";
import { JobRowsChart } from "./components/JobRowsChart";

function App() {
  const [jobIds, setJobIds] = useState<string[]>([]);
  const [selectedJobId, setSelectedJobId] = useState<string | null>(null);

  const { data: selectedJob } = useJob(selectedJobId);

  return (
    <div className="mx-auto flex max-w-4xl flex-col gap-6 p-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900">Books to Scrape — monitor</h1>
        <p className="text-sm text-slate-500">
          Triggers scrape jobs against the backend API and shows results as they land.
        </p>
      </header>

      <JobForm
        onCreated={(jobId) => {
          setJobIds((prev) => [jobId, ...prev]);
          setSelectedJobId(jobId);
        }}
      />

      <section className="grid grid-cols-1 gap-6 md:grid-cols-[240px_1fr]">
        <div>
          <h2 className="mb-2 text-sm font-semibold text-slate-700">Jobs</h2>
          <JobsList jobIds={jobIds} selectedJobId={selectedJobId} onSelect={setSelectedJobId} />
        </div>

        <div className="flex flex-col gap-4">
          {selectedJobId === null ? (
            <p className="text-sm text-slate-500">Select a job to see its results.</p>
          ) : (
            <>
              {selectedJob?.status === "failed" && (
                <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">
                  Job failed: {selectedJob.error_message}
                </p>
              )}
              {selectedJob?.status === "succeeded" && <JobRowsChart job={selectedJob} />}
              <ResultsTable jobId={selectedJobId} jobSucceeded={selectedJob?.status === "succeeded"} />
            </>
          )}
        </div>
      </section>
    </div>
  );
}

export default App;
