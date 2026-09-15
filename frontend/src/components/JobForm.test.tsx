import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { JobForm } from "./JobForm";
import { withQueryClient } from "../test/queryWrapper";
import * as api from "../api";

describe("JobForm", () => {
  it("submits max_pages and reports the created job id", async () => {
    const createJobSpy = vi.spyOn(api, "createJob").mockResolvedValue({
      id: "job-123",
      status: "queued",
      max_pages: 3,
      created_at: "2026-01-01T00:00:00Z",
      started_at: null,
      finished_at: null,
      rows_new: 0,
      rows_changed: 0,
      rows_unchanged: 0,
      rows_rejected: 0,
      error_message: null,
    });

    const onCreated = vi.fn();
    render(withQueryClient(<JobForm onCreated={onCreated} />));

    fireEvent.change(screen.getByLabelText(/catalogue pages/i), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: /start scrape job/i }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("job-123"));
    expect(createJobSpy).toHaveBeenCalledWith(3);
  });

  it("shows an error message when job creation fails", async () => {
    vi.spyOn(api, "createJob").mockRejectedValue(new Error("robots.txt disallows"));

    render(withQueryClient(<JobForm onCreated={vi.fn()} />));
    fireEvent.click(screen.getByRole("button", { name: /start scrape job/i }));

    expect(await screen.findByText(/robots.txt disallows/i)).toBeInTheDocument();
  });
});
