import { render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { ResultsTable } from "./ResultsTable";
import { withQueryClient } from "../test/queryWrapper";
import * as api from "../api";

const SAMPLE = {
  total: 2,
  limit: 10,
  offset: 0,
  items: [
    { url: "u1", title: "A Light in the Attic", price: 51.77, rating: 3, availability: "In stock", recorded_at: "2026-01-01T00:00:00Z" },
    { url: "u2", title: "Unsellable Vaporware", price: 5.0, rating: 0, availability: "Out of stock", recorded_at: "2026-01-01T00:00:00Z" },
  ],
};

describe("ResultsTable", () => {
  it("shows a placeholder before the job has succeeded", () => {
    render(withQueryClient(<ResultsTable jobId="job-1" jobSucceeded={false} />));
    expect(screen.getByText(/results will appear/i)).toBeInTheDocument();
  });

  it("renders rows once the job has succeeded", async () => {
    vi.spyOn(api, "getResults").mockResolvedValue(SAMPLE);

    render(withQueryClient(<ResultsTable jobId="job-1" jobSucceeded={true} />));

    expect(await screen.findByText("A Light in the Attic")).toBeInTheDocument();
    expect(screen.getByText("Unsellable Vaporware")).toBeInTheDocument();
    expect(screen.getByText(/2 rows total/)).toBeInTheDocument();
  });

  it("links the CSV export to the correct job", async () => {
    vi.spyOn(api, "getResults").mockResolvedValue(SAMPLE);
    render(withQueryClient(<ResultsTable jobId="job-1" jobSucceeded={true} />));

    await waitFor(() => screen.getByText("Download CSV"));
    expect(screen.getByText("Download CSV")).toHaveAttribute("href", api.exportUrl("job-1"));
  });
});
