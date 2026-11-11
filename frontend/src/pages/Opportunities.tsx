import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { type Item, type Label, api } from "../api";
import { DataTable, downloadCsv } from "../components/DataTable";
import { Hint } from "../components/Hint";
import { useApp } from "../context";
import { useData, useStored } from "../hooks";
import { LABELS } from "../strings";
import { itemColumns } from "./itemColumns";

const KEYS = ["name", "group", "price_now", "sell_ref", "flip_profit", "flip_margin", "my_sales_per_day",
  "flip_profit_day", "volatility", "disc_ref", "label", "flags"] as const;

interface Filters {
  group: string;
  label: string;
  search: string;
  minSales: number;
  hideWarnings: boolean;
  scope: "tracked" | "all";
}

const DEFAULTS: Filters = { group: "", label: "", search: "", minSales: 0, hideWarnings: false, scope: "tracked" };

export default function Opportunities() {
  const { groups, version } = useApp();
  const [f, setF] = useStored<Filters>("opportunities.filters", DEFAULTS);
  const [sorting, setSorting] = useStored("opportunities.sort", [{ id: "flip_profit_day", desc: true }]);
  const { data, error } = useData(() => api.items(f.scope), [f.scope], version);
  const navigate = useNavigate();

  const rows = useMemo(() => {
    const q = f.search.trim().toLowerCase();
    return (data ?? []).filter((i: Item) =>
      (!f.group || i.groups.includes(f.group)) &&
      (!f.label || i.label === f.label) &&
      (!q || i.name.toLowerCase().includes(q)) &&
      (i.my_sales_per_day ?? 0) >= f.minSales &&
      (!f.hideWarnings || !i.flags.some((x) => ["bubble", "possible_misprice", "stale", "no_volume"].includes(x))));
  }, [data, f]);

  const columns = useMemo(() => itemColumns([...KEYS], groups), [groups]);

  const set = <K extends keyof Filters>(k: K, v: Filters[K]) => setF((old) => ({ ...old, [k]: v }));

  return (
    <section>
      <div className="page-head">
        <h1>Opportunities</h1>
        <p className="lead">
          Items you could buy at today's cheapest listing and resell at their usual price, ranked by what that could
          make per day. Click any row for the full picture before acting.
          <Hint text="Flipping depends on the price returning to normal and on buyers showing up. Check volatility, warnings and the price chart first." />
        </p>
      </div>
      <div className="filters">
        <select value={f.group} onChange={(e) => set("group", e.target.value)}>
          <option value="">All groups</option>
          {groups.map((g) => <option key={g.key} value={g.key}>{g.title}</option>)}
        </select>
        <select value={f.label} onChange={(e) => set("label", e.target.value)}>
          <option value="">Any verdict</option>
          {(Object.keys(LABELS) as Label[]).map((l) => <option key={l} value={l}>{LABELS[l]}</option>)}
        </select>
        <input placeholder="Search items" value={f.search} onChange={(e) => set("search", e.target.value)} />
        <label>
          Min sales/day
          <input type="number" min={0} step={0.5} value={f.minSales}
            onChange={(e) => set("minSales", Number(e.target.value) || 0)} style={{ width: 70 }} />
        </label>
        <label className="check">
          <input type="checkbox" checked={f.hideWarnings} onChange={(e) => set("hideWarnings", e.target.checked)} />
          Hide risky items
        </label>
        <label className="check">
          <input type="checkbox" checked={f.scope === "all"} onChange={(e) => set("scope", e.target.checked ? "all" : "tracked")} />
          Include items outside my professions
        </label>
        <span className="spacer" />
        <button onClick={() => setF(DEFAULTS)}>Reset</button>
        <button onClick={() => downloadCsv("simsar-opportunities", rows, columns)}>Export CSV</button>
      </div>
      {error && <div className="error-banner">{error}</div>}
      {!data ? <div className="loading">Loading...</div> : (
        <DataTable rows={rows} columns={columns} sorting={sorting} onSortingChange={setSorting}
          onRowClick={(r) => navigate(`/item/${r.item_id}`)} />
      )}
    </section>
  );
}
