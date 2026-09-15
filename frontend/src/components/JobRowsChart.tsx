import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { Job } from "../api";

export function JobRowsChart({ job }: { job: Job }) {
  const data = [
    { name: "New", rows: job.rows_new },
    { name: "Changed", rows: job.rows_changed },
    { name: "Unchanged", rows: job.rows_unchanged },
    { name: "Rejected", rows: job.rows_rejected },
  ];

  return (
    <div className="h-48 w-full rounded-lg border border-slate-200 bg-white p-3">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data}>
          <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
          <XAxis dataKey="name" tick={{ fontSize: 12 }} />
          <YAxis allowDecimals={false} tick={{ fontSize: 12 }} />
          <Tooltip />
          <Bar dataKey="rows" fill="#4f46e5" radius={[4, 4, 0, 0]} />
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}
