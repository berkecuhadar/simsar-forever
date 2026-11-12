import type { ColumnDef } from "@tanstack/react-table";
import { Skeleton } from "../components/Feedback";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { type InventoryItem, api } from "../api";
import { Flags } from "../components/Badges";
import { DataTable, downloadCsv } from "../components/DataTable";
import { Hint } from "../components/Hint";
import { ItemIcon, ItemName } from "../components/Icons";
import { useApp } from "../context";
import { Money, ago, num } from "../format";
import { useData, useStored } from "../hooks";

const CLASS_COLORS: Record<string, string> = {
  WARRIOR: "#c69b6d", PALADIN: "#f48cba", HUNTER: "#aad372", ROGUE: "#fff468", PRIEST: "#ffffff",
  SHAMAN: "#0070dd", MAGE: "#3fc7eb", WARLOCK: "#8788ee", DRUID: "#ff7c0a",
};

const SELL_WHERE: Record<string, { label: string; hint: string }> = {
  auction: { label: "Auction", hint: "Worth more on the auction house than at a vendor." },
  vendor: { label: "Vendor", hint: "A vendor pays more than the auction house would leave you, or it has no auction price." },
  bound: { label: "Bound", hint: "Soulbound: it can only be sold to a vendor." },
  unknown: { label: "No price", hint: "Neither an auction nor a vendor price is known." },
};

interface Row extends InventoryItem {
  who: string[];
}

function aggregate(items: InventoryItem[], charNames: Record<string, string>): Row[] {
  const by = new Map<number, Row>();
  for (const it of items) {
    const r = by.get(it.item_id);
    if (!r) {
      by.set(it.item_id, { ...it, who: [charNames[it.char_key] ?? it.char_key] });
      continue;
    }
    r.bags += it.bags;
    r.bank += it.bank;
    r.count += it.count;
    r.bound += it.bound;
    r.value += it.value;
    r.ah_value = (r.ah_value ?? 0) + (it.ah_value ?? 0);
    r.vendor_value = (r.vendor_value ?? 0) + (it.vendor_value ?? 0);
    r.who.push(charNames[it.char_key] ?? it.char_key);
    const tradable = r.count - r.bound;
    r.days_to_sell = r.my_sales_per_day && tradable ? tradable / r.my_sales_per_day : null;
  }
  return [...by.values()];
}

function num0(v: number | null | undefined) {
  return v ? num(v, 0) : <span className="muted">-</span>;
}

export default function Inventory() {
  const { version } = useApp();
  const { data, error } = useData(api.inventory, [], version);
  const [f, setF] = useStored("inventory.filters", { char: "", location: "", search: "", hideBound: false });
  const [sorting, setSorting] = useStored("inventory.sort", [{ id: "value", desc: true }]);
  const navigate = useNavigate();

  const charNames = useMemo(
    () => Object.fromEntries((data?.characters ?? []).map((c) => [c.char_key, c.name ?? c.char_key])), [data]);

  const rows = useMemo(() => {
    if (!data) return [];
    const q = f.search.trim().toLowerCase();
    let items = data.items.filter((i) => !f.char || i.char_key === f.char);
    items = items.map((i) => {
      if (!f.location) return i;
      const share = (f.location === "bags" ? i.bags : i.bank) / i.count;
      return { ...i, count: f.location === "bags" ? i.bags : i.bank, value: i.value * share,
        ah_value: i.ah_value === null ? null : i.ah_value * share,
        bags: f.location === "bags" ? i.bags : 0, bank: f.location === "bank" ? i.bank : 0 };
    }).filter((i) => i.count > 0);
    const out = f.char ? items.map((i) => ({ ...i, who: [charNames[i.char_key] ?? i.char_key] })) : aggregate(items, charNames);
    return out.filter((r) => (!q || r.name.toLowerCase().includes(q)) && (!f.hideBound || r.sell_where !== "bound"));
  }, [data, f, charNames]);

  const totals = useMemo(() => ({
    value: rows.reduce((s, r) => s + r.value, 0),
    ah: rows.reduce((s, r) => s + (r.ah_value ?? 0), 0),
    money: (data?.characters ?? []).filter((c) => !f.char || c.char_key === f.char).reduce((s, c) => s + (c.money ?? 0), 0),
  }), [rows, data, f.char]);

  const columns = useMemo<ColumnDef<Row, unknown>[]>(() => [
    { id: "name", header: "Item", accessorFn: (r) => r.name, meta: { align: "left", csv: (r: Row) => r.name },
      cell: ({ row }) => (
        <span className="item-name">
          <ItemIcon id={row.original.icon_id} quality={row.original.quality} />
          <ItemName name={row.original.name} quality={row.original.quality} />
        </span>
      ) },
    { id: "who", header: "Character", accessorFn: (r) => r.who.join(", "), enableSorting: false,
      meta: { align: "left", csv: (r: Row) => r.who.join("; ") },
      cell: ({ row }) => <span className="muted small">{row.original.who.join(", ")}</span> },
    { id: "bags", header: "Bags", accessorFn: (r) => r.bags, meta: { csv: (r: Row) => r.bags }, cell: ({ row }) => num0(row.original.bags) },
    { id: "bank", header: "Bank", accessorFn: (r) => r.bank, meta: { csv: (r: Row) => r.bank }, cell: ({ row }) => num0(row.original.bank) },
    { id: "count", header: "Total", accessorFn: (r) => r.count, meta: { csv: (r: Row) => r.count }, cell: ({ row }) => num(row.original.count, 0) },
    { id: "unit_ah", header: "You keep (each)", accessorFn: (r) => r.unit_ah,
      meta: { hint: "What one sale on the auction house leaves you today, after the cut.", csv: (r: Row) => r.unit_ah },
      cell: ({ row }) => <Money value={row.original.unit_ah} /> },
    { id: "vendor_sell", header: "Vendor (each)", accessorFn: (r) => r.vendor_sell,
      meta: { hint: "What a vendor pays for one.", csv: (r: Row) => r.vendor_sell },
      cell: ({ row }) => <Money value={row.original.vendor_sell} /> },
    { id: "value", header: "Value", accessorFn: (r) => r.value,
      meta: { hint: "All units sold where they fetch more: auction house (after the cut) or vendor. Bound units at the vendor price.", csv: (r: Row) => Math.round(r.value) },
      cell: ({ row }) => <b><Money value={row.original.value} /></b> },
    { id: "sell_where", header: "Sell at", accessorFn: (r) => r.sell_where,
      meta: { hint: "Where this item is worth more.", align: "left", csv: (r: Row) => r.sell_where },
      cell: ({ row }) => {
        const s = SELL_WHERE[row.original.sell_where];
        return <Hint text={s.hint} plain><span className={`badge where-${row.original.sell_where}`}>{s.label}</span></Hint>;
      } },
    { id: "my_sales_per_day", header: "Sales/day", accessorFn: (r) => r.my_sales_per_day,
      meta: { hint: "How many you can expect to sell per day on your realm.", csv: (r: Row) => r.my_sales_per_day },
      cell: ({ row }) => num(row.original.my_sales_per_day) },
    { id: "days_to_sell", header: "Days to sell", accessorFn: (r) => r.days_to_sell ?? Infinity,
      meta: { hint: "How long selling everything you hold would take at that pace.", csv: (r: Row) => r.days_to_sell },
      cell: ({ row }) => num(row.original.days_to_sell) },
    { id: "flags", header: "Warnings", enableSorting: false, accessorFn: (r) => r.flags.join(" "),
      meta: { align: "left" }, cell: ({ row }) => <Flags flags={row.original.flags} /> },
  ], []);

  const set = (k: string, v: unknown) => setF((old) => ({ ...old, [k]: v }));

  if (error) return <div className="error-banner">{error}</div>;
  if (!data) return <Skeleton />;

  return (
    <section>
      <div className="page-head">
        <h1>Bags and bank</h1>
        <p className="lead">
          Everything your characters carry, valued at what you would keep selling it today. Bags update whenever they
          change in game, the bank whenever you open it; the game writes both to disk on <code>/reload</code> or logout.
          Prices update by themselves as new market data arrives.
        </p>
      </div>

      {data.characters.length === 0 ? (
        <div className="card empty-state">
          <h3>No characters yet</h3>
          <p>Log in with SimsarForeverExport enabled, open your bags and your bank, then type <code>/reload</code>.</p>
        </div>
      ) : (
        <>
          <div className="char-grid">
            <button className={`char-card ${!f.char ? "selected" : ""}`} onClick={() => set("char", "")}>
              <div className="char-name">All characters</div>
              <div className="char-value"><Money value={data.characters.reduce((s, c) => s + (c.value ?? 0), 0)} /></div>
              <div className="muted small">
                items, plus <Money value={data.characters.reduce((s, c) => s + (c.money ?? 0), 0)} /> gold
              </div>
            </button>
            {data.characters.map((c) => (
              <button key={c.char_key} className={`char-card ${f.char === c.char_key ? "selected" : ""}`}
                onClick={() => set("char", f.char === c.char_key ? "" : c.char_key)}>
                <div className="char-name" style={{ color: CLASS_COLORS[c.class ?? ""] }}>{c.name}</div>
                <div className="char-value"><Money value={c.value ?? 0} /></div>
                <div className="muted small">
                  <Money value={c.money ?? 0} /> gold · bags {ago(c.bags_at)} · bank {c.bank_at ? ago(c.bank_at) : "never opened"}
                </div>
              </button>
            ))}
          </div>

          <div className="filters">
            <select value={f.location} onChange={(e) => set("location", e.target.value)}>
              <option value="">Bags and bank</option>
              <option value="bags">Bags only</option>
              <option value="bank">Bank only</option>
            </select>
            <input placeholder="Search items" value={f.search} onChange={(e) => set("search", e.target.value)} />
            <label className="check">
              <input type="checkbox" checked={f.hideBound} onChange={(e) => set("hideBound", e.target.checked)} />
              Hide soulbound
            </label>
            <span className="spacer" />
            <span className="small">
              {rows.length} items · value <b><Money value={totals.value} /></b>
              <Hint text="Value of the listed items, each sold where it fetches more, plus the gold on hand below." />
              {" "}· gold <Money value={totals.money} />
            </span>
            <button onClick={() => downloadCsv("simsar-forever-inventory", rows, columns)}>Export CSV</button>
          </div>

          <DataTable rows={rows} columns={columns} sorting={sorting} onSortingChange={setSorting}
            onRowClick={(r) => navigate(`/item/${r.item_id}`)} empty="Nothing matches these filters." />
        </>
      )}
    </section>
  );
}
