import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { SiteForm } from "./SiteForm";
import { withQueryClient } from "../test/queryWrapper";
import * as api from "../api";

const SAMPLE_SITE: api.SiteDefinition = {
  id: "site-1",
  name: "my-shop",
  base_url: "https://example.com/",
  list_url_template: "https://example.com/products?page={page}",
  item_selector: "article.product",
  key_selector: "a",
  key_attr: "href",
  fields: [{ name: "title", selector: "h2", attr: "text", type: "text", required: true }],
  max_pages: 5,
  created_at: "2026-01-01T00:00:00Z",
};

describe("SiteForm", () => {
  it("submits the site config and reports the created site id", async () => {
    const createSiteSpy = vi.spyOn(api, "createSite").mockResolvedValue(SAMPLE_SITE);
    const onCreated = vi.fn();

    render(withQueryClient(<SiteForm onCreated={onCreated} />));

    fireEvent.change(screen.getByPlaceholderText("my-shop"), { target: { value: "my-shop" } });
    fireEvent.change(screen.getByPlaceholderText("https://example.com/"), { target: { value: "https://example.com/" } });
    fireEvent.change(screen.getByPlaceholderText("https://example.com/products?page={page}"), {
      target: { value: "https://example.com/products?page={page}" },
    });
    fireEvent.change(screen.getByPlaceholderText("article.product"), { target: { value: "article.product" } });
    fireEvent.change(screen.getByPlaceholderText("name (e.g. price)"), { target: { value: "title" } });
    fireEvent.change(screen.getByPlaceholderText("CSS selector"), { target: { value: "h2" } });

    fireEvent.click(screen.getByRole("button", { name: /save site/i }));

    await waitFor(() => expect(onCreated).toHaveBeenCalledWith("site-1"));
    expect(createSiteSpy).toHaveBeenCalledWith(
      expect.objectContaining({
        name: "my-shop",
        base_url: "https://example.com/",
        fields: [expect.objectContaining({ name: "title", selector: "h2" })],
      }),
    );
  });

  it("can add and remove extra field rows", () => {
    render(withQueryClient(<SiteForm onCreated={vi.fn()} />));

    expect(screen.getAllByPlaceholderText("name (e.g. price)")).toHaveLength(1);
    fireEvent.click(screen.getByText("+ add field"));
    expect(screen.getAllByPlaceholderText("name (e.g. price)")).toHaveLength(2);

    fireEvent.click(screen.getAllByText("remove")[0]);
    expect(screen.getAllByPlaceholderText("name (e.g. price)")).toHaveLength(1);
  });
});
