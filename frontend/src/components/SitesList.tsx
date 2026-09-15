import { useSites } from "../hooks";

export function SitesList({ selectedSiteId, onSelect }: { selectedSiteId: string | null; onSelect: (siteId: string) => void }) {
  const { data: sites, isLoading } = useSites();

  if (isLoading) return <p className="text-sm text-slate-500">Loading sites…</p>;
  if (!sites || sites.length === 0) {
    return <p className="text-sm text-slate-500">No sites saved yet — add one above.</p>;
  }

  return (
    <div className="flex flex-col gap-2">
      {sites.map((site) => (
        <button
          key={site.id}
          onClick={() => onSelect(site.id)}
          className={`flex flex-col items-start rounded-md border px-3 py-2 text-left text-sm ${
            site.id === selectedSiteId ? "border-indigo-400 bg-indigo-50" : "border-slate-200 bg-white hover:bg-slate-50"
          }`}
        >
          <span className="font-medium text-slate-800">{site.name}</span>
          <span className="text-xs text-slate-500">{site.fields.map((f) => f.name).join(", ")}</span>
        </button>
      ))}
    </div>
  );
}
