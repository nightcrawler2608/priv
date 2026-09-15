import { useState } from "react";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { createSite, detectSite, type DetectSiteResponse, type FieldConfig, type FieldType } from "../api";

export function QuickAddSite({ onCreated }: { onCreated: (siteId: string) => void }) {
  const [url, setUrl] = useState("");
  const [detected, setDetected] = useState<DetectSiteResponse | null>(null);
  const [name, setName] = useState("");
  const [fields, setFields] = useState<FieldConfig[]>([]);
  const queryClient = useQueryClient();

  const detectMutation = useMutation({
    mutationFn: () => detectSite(url),
    onSuccess: (result) => {
      setDetected(result);
      setName(result.name);
      setFields(result.fields);
    },
  });

  const saveMutation = useMutation({
    mutationFn: () => {
      if (!detected) throw new Error("nothing detected yet");
      return createSite({
        name,
        base_url: detected.base_url,
        list_url_template: detected.list_url_template,
        item_selector: detected.item_selector,
        key_selector: detected.key_selector,
        key_attr: detected.key_attr,
        fields,
        max_pages: detected.max_pages,
      });
    },
    onSuccess: (site) => {
      queryClient.invalidateQueries({ queryKey: ["sites"] });
      setDetected(null);
      setUrl("");
      onCreated(site.id);
    },
  });

  function updateField(index: number, patch: Partial<FieldConfig>) {
    setFields((prev) => prev.map((f, i) => (i === index ? { ...f, ...patch } : f)));
  }

  return (
    <div className="flex flex-col gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm">
      <h3 className="text-sm font-semibold text-slate-700">Paste a URL — no CSS knowledge needed</h3>

      <form
        className="flex gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          detectMutation.mutate();
        }}
      >
        <input
          required
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://example.com/products"
          className="flex-1 rounded-md border border-slate-300 px-2 py-1.5 text-sm"
        />
        <button
          type="submit"
          disabled={detectMutation.isPending}
          className="rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
        >
          {detectMutation.isPending ? "Detecting…" : "Detect"}
        </button>
      </form>

      {detectMutation.isError && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-sm text-red-700">{(detectMutation.error as Error).message}</p>
      )}

      {detected && (
        <div className="flex flex-col gap-3 border-t border-slate-100 pt-3">
          <p className="text-sm text-slate-600">
            Found <strong>{detected.item_count}</strong> repeated items on that page. Review the guessed fields below, then save.
          </p>

          <label className="flex flex-col gap-1 text-sm text-slate-700">
            Site name
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              className="rounded-md border border-slate-300 px-2 py-1.5 text-sm"
            />
          </label>

          <div className="flex flex-col gap-2">
            <span className="text-sm font-medium text-slate-700">Detected fields (edit if anything looks wrong)</span>
            {fields.map((field, i) => (
              <div key={i} className="grid grid-cols-2 gap-2 rounded-md border border-slate-100 bg-slate-50 p-2 sm:grid-cols-4">
                <input
                  value={field.name}
                  onChange={(e) => updateField(i, { name: e.target.value })}
                  className="rounded border border-slate-300 px-2 py-1 text-xs"
                />
                <input
                  value={field.selector}
                  onChange={(e) => updateField(i, { selector: e.target.value })}
                  className="rounded border border-slate-300 px-2 py-1 text-xs font-mono"
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
              </div>
            ))}
          </div>

          {detected.preview.length > 0 && (
            <div className="overflow-x-auto">
              <span className="text-xs font-medium text-slate-500">Preview (first {detected.preview.length} rows)</span>
              <table className="mt-1 w-full min-w-max overflow-hidden rounded-md border border-slate-200 text-left text-sm">
                <thead className="bg-slate-50 text-slate-600">
                  <tr>
                    {Object.keys(detected.preview[0]).map((col) => (
                      <th key={col} className="px-3 py-1.5">{col}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {detected.preview.map((row, i) => (
                    <tr key={i} className="border-t border-slate-100">
                      {Object.keys(detected.preview[0]).map((col) => (
                        <td key={col} className="px-3 py-1.5">{String(row[col] ?? "")}</td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          <button
            onClick={() => saveMutation.mutate()}
            disabled={saveMutation.isPending}
            className="self-start rounded-md bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            {saveMutation.isPending ? "Saving…" : "Save site"}
          </button>
          {saveMutation.isError && <p className="text-sm text-red-600">{(saveMutation.error as Error).message}</p>}
        </div>
      )}
    </div>
  );
}
