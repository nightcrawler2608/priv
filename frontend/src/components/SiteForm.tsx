import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createSite, type FieldConfig, type FieldType } from "../api";

const EMPTY_FIELD: FieldConfig = { name: "", selector: "", attr: "text", type: "text", required: true };

export function SiteForm({ onCreated }: { onCreated: (siteId: string) => void }) {
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [listUrlTemplate, setListUrlTemplate] = useState("");
  const [itemSelector, setItemSelector] = useState("");
  const [keySelector, setKeySelector] = useState("");
  const [maxPages, setMaxPages] = useState(5);
  const [fields, setFields] = useState<FieldConfig[]>([{ ...EMPTY_FIELD }]);

  const queryClient = useQueryClient();

  const mutation = useMutation({
    mutationFn: () =>
      createSite({
        name,
        base_url: baseUrl,
        list_url_template: listUrlTemplate,
        item_selector: itemSelector,
        key_selector: keySelector.trim() === "" ? null : keySelector,
        key_attr: "href",
        fields,
        max_pages: maxPages,
      }),
    onSuccess: (site) => {
      queryClient.invalidateQueries({ queryKey: ["sites"] });
      onCreated(site.id);
    },
  });

  function updateField(index: number, patch: Partial<FieldConfig>) {
    setFields((prev) => prev.map((f, i) => (i === index ? { ...f, ...patch } : f)));
  }

  return (
    <form
      className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm"
      onSubmit={(e) => {
        e.preventDefault();
        mutation.mutate();
      }}
    >
      <h3 className="text-sm font-semibold text-slate-700">Add a site</h3>

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="flex flex-col gap-1 text-sm text-slate-700">
          Site name
          <input
            required
            value={name}
            onChange={(e) => setName(e.target.value)}
            className="rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            placeholder="my-shop"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-slate-700">
          Base URL
          <input
            required
            value={baseUrl}
            onChange={(e) => setBaseUrl(e.target.value)}
            className="rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            placeholder="https://example.com/"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-slate-700 sm:col-span-2">
          List page URL template (must contain <code>{"{page}"}</code>)
          <input
            required
            value={listUrlTemplate}
            onChange={(e) => setListUrlTemplate(e.target.value)}
            className="rounded-md border border-slate-300 px-2 py-1.5 text-sm font-mono"
            placeholder="https://example.com/products?page={page}"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-slate-700">
          Item selector (CSS, one per row/card)
          <input
            required
            value={itemSelector}
            onChange={(e) => setItemSelector(e.target.value)}
            className="rounded-md border border-slate-300 px-2 py-1.5 text-sm font-mono"
            placeholder="article.product"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-slate-700">
          Key selector (link, optional but recommended)
          <input
            value={keySelector}
            onChange={(e) => setKeySelector(e.target.value)}
            className="rounded-md border border-slate-300 px-2 py-1.5 text-sm font-mono"
            placeholder="a"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-slate-700">
          Max pages
          <input
            type="number"
            min={1}
            max={200}
            value={maxPages}
            onChange={(e) => setMaxPages(Number(e.target.value))}
            className="w-32 rounded-md border border-slate-300 px-2 py-1.5 text-sm"
          />
        </label>
      </div>

      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between">
          <span className="text-sm font-medium text-slate-700">Fields to extract</span>
          <button
            type="button"
            onClick={() => setFields((prev) => [...prev, { ...EMPTY_FIELD }])}
            className="text-xs font-medium text-indigo-600 hover:underline"
          >
            + add field
          </button>
        </div>

        {fields.map((field, i) => (
          <div key={i} className="grid grid-cols-2 gap-2 rounded-md border border-slate-100 bg-slate-50 p-2 sm:grid-cols-6">
            <input
              required
              placeholder="name (e.g. price)"
              value={field.name}
              onChange={(e) => updateField(i, { name: e.target.value })}
              className="rounded border border-slate-300 px-2 py-1 text-xs sm:col-span-2"
            />
            <input
              required
              placeholder="CSS selector"
              value={field.selector}
              onChange={(e) => updateField(i, { selector: e.target.value })}
              className="rounded border border-slate-300 px-2 py-1 text-xs font-mono sm:col-span-2"
            />
            <select
              value={field.attr}
              onChange={(e) => updateField(i, { attr: e.target.value })}
              className="rounded border border-slate-300 px-2 py-1 text-xs"
            >
              <option value="text">text</option>
              <option value="href">href</option>
              <option value="src">src</option>
              <option value="title">title</option>
              <option value="alt">alt</option>
            </select>
            <select
              value={field.type}
              onChange={(e) => updateField(i, { type: e.target.value as FieldType })}
              className="rounded border border-slate-300 px-2 py-1 text-xs"
            >
              <option value="text">text</option>
              <option value="number">number</option>
            </select>
            <label className="col-span-2 flex items-center gap-1 text-xs text-slate-600 sm:col-span-1">
              <input
                type="checkbox"
                checked={field.required}
                onChange={(e) => updateField(i, { required: e.target.checked })}
              />
              required
            </label>
            {fields.length > 1 && (
              <button
                type="button"
                onClick={() => setFields((prev) => prev.filter((_, idx) => idx !== i))}
                className="text-xs text-red-600 hover:underline"
              >
                remove
              </button>
            )}
          </div>
        ))}
      </div>

      <button
        type="submit"
        disabled={mutation.isPending}
        className="self-start rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
      >
        {mutation.isPending ? "Saving…" : "Save site"}
      </button>
      {mutation.isError && <p className="text-sm text-red-600">{(mutation.error as Error).message}</p>}
    </form>
  );
}
