import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { GenericResultsTable } from "./GenericResultsTable";
import { withQueryClient } from "../test/queryWrapper";
import * as api from "../api";

const SITE: api.SiteDefinition = {
  id: "site-1",
  name: "my-shop",
  base_url: "https://example.com/",
  list_url_template: "https://example.com/products?page={page}",
  item_selector: "article.product",
  key_selector: "a",
  key_attr: "href",
  fields: [
    { name: "title", selector: "h2", attr: "text", type: "text", required: true },
    { name: "price", selector: ".price", attr: "text", type: "number", required: true },
  ],
  max_pages: 5,
  created_at: "2026-01-01T00:00:00Z",
};

describe("GenericResultsTable", () => {
  it("shows a placeholder before the job has succeeded", () => {
    render(withQueryClient(<GenericResultsTable site={SITE} jobId="job-1" jobSucceeded={false} />));
    expect(screen.getByText(/results will appear/i)).toBeInTheDocument();
  });

  it("renders dynamic columns matching the site's configured fields", async () => {
    vi.spyOn(api, "getSiteResults").mockResolvedValue({
      total: 1,
      limit: 10,
      offset: 0,
      items: [{ key: "k1", data: { title: "Widget", price: 9.99 }, recorded_at: "2026-01-01T00:00:00Z" }],
    });

    render(withQueryClient(<GenericResultsTable site={SITE} jobId="job-1" jobSucceeded={true} />));

    expect(await screen.findByText("Widget")).toBeInTheDocument();
    expect(screen.getByText("9.99")).toBeInTheDocument();
    expect(screen.getByText("title")).toBeInTheDocument();
    expect(screen.getByText("price")).toBeInTheDocument();
  });
});
