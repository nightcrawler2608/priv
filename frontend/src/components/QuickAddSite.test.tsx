import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { QuickAddSite } from "./QuickAddSite";
import { withQueryClient } from "../test/queryWrapper";
import * as api from "../api";

const DETECTED: api.DetectSiteResponse = {
  name: "example.com",
  base_url: "https://example.com/",
  list_url_template: "https://example.com/products",
  item_selector: "article.product",
  key_selector: "a",
  key_attr: "href",
  fields: [
    { name: "title", selector: "h2", attr: "text", type: "text", required: false },
    { name: "price", selector: ".price", attr: "text", type: "number", required: false },
  ],
  max_pages: 1,
  item_count: 12,
  preview: [{ title: "Widget", price: 9.99 }],
};

describe("QuickAddSite", () => {
  it("detects a URL and shows a preview with the guessed fields", async () => {
    vi.spyOn(api, "detectSite").mockResolvedValue(DETECTED);

    render(withQueryClient(<QuickAddSite onCreated={vi.fn()} />));

    fireEvent.change(screen.getByPlaceholderText("https://example.com/products"), {
      target: { value: "https://example.com/products" },
    });
    fireEvent.click(screen.getByRole("button", { name: /detect/i }));

    expect(await screen.findByText(/found/i)).toBeInTheDocument();
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByDisplayValue("title")).toBeInTheDocument();
    expect(screen.getByText("Widget")).toBeInTheDocument();
  });

  it("saves the detected site and reports the new id", async () => {
    vi.spyOn(api, "detectSite").mockResolvedValue(DETECTED);
    const createSiteSpy = vi.spyOn(api, "createSite").mockResolvedValue({
      ...DETECTED,
      id: "site-42",
      created_at: "2026-01-01T00:00:00Z",
    });
    const onCreated = vi.fn();

    render(withQueryClient(<QuickAddSite onCreated={onCreated} />));

    fireEvent.change(screen.getByPlaceholderText("https://example.com/products"), {
      target: { value: "https://example.com/products" },
    });
    fireEvent.click(screen.getByRole("button", { name: /detect/i }));
    await screen.findByText(/found/i);

    fireEvent.click(screen.getByRole("button", { name: /save site/i }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("site-42"));
    expect(createSiteSpy).toHaveBeenCalledWith(
      expect.objectContaining({ item_selector: "article.product", max_pages: 1 }),
    );
  });
});
