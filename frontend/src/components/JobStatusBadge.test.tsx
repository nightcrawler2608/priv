import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { JobStatusBadge } from "./JobStatusBadge";

describe("JobStatusBadge", () => {
  it("shows the status text", () => {
    render(<JobStatusBadge status="running" />);
    expect(screen.getByText("running")).toBeInTheDocument();
  });

  it("uses a distinct style per status", () => {
    const { rerender } = render(<JobStatusBadge status="succeeded" />);
    expect(screen.getByText("succeeded").className).toContain("emerald");

    rerender(<JobStatusBadge status="failed" />);
    expect(screen.getByText("failed").className).toContain("red");
  });
});
