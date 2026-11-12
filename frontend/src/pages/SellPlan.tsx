import type { ColumnDef } from "@tanstack/react-table";
import { useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { type AdviceKind, type InventoryItem, type Plan, api } from "../api";
import { DataTable, downloadCsv } from "../components/DataTable";
import { Skeleton } from "../components/Feedback";
import { Hint } from "../components/Hint";
import { ItemIcon, ItemName } from "../components/Icons";
import { useApp } from "../context";
import { Money, num, pct } from "../format";

const perDay = (v: number | null | undefined) => num(v, v !== null && v !== undefined && v >= 10 ? 0 : 1);
import { useData, useStored } from "../hooks";
import { CLASS_COLORS } from "./Inventory";

export const ADVICE: Record<AdviceKind, { label: string; hint: string; order: number }> = {
  hold: { label: "Hold", order: 0,
    hint: "The forecast expects a rise worth waiting for, and the forecasts have beaten 'no change' in the backtest." },
  sell: { label: "Sell now", order: 1, hint: "List on the auction house now; waiting is not expected to pay." },
  gradual: { label: "Sell a few at a time", order: 2,
    hint: "You hold more than the market buys in a few days. Listing everything at once means undercutting yourself." },
  vendor: { label: "Vendor", order: 3, hint: "A vendor pays at least what an auction sale leaves you after the cut." },
  bound: { label: "Soulbound", order: 4, hint: "Bound to the character: only a vendor takes it." },
  none: { label: "No price", order: 5, hint: "Neither an auction nor a vendor price is known." },
};

interface Row extends InventoryItem {
  who: string[];
  advice: AdviceKind;
}

function why(r: Row, gradualDays: number): string {
  const p = r.plan;
  const tradable = r.count - r.bound;
  switch (r.advice) {
    case "hold":
      return `Expected ${pct(p?.expected_change, 0, true)} within ${p?.horizon} days (80% range ${pct(p?.low, 0, true)} to ${pct(p?.high, 0, true)}), ${pct(p?.p_up)} chance of a rise.`;
    case "vendor":
      return r.unit_ah ? "A vendor pays more than an auction sale leaves you." : "No auction price; a vendor buys it.";
    case "gradual":
      return `You hold ${num(tradable, 0)}; about ${perDay(r.my_sales_per_day)} sell per day for you, so about ${num(r.days_to_sell, 0)} days of sales (more than ${gradualDays}).`;
    case "bound":
      return "Soulbound.";
    case "none":
      return "No auction or vendor price known.";
    default:
      if (p?.expected_change !== null && p?.expected_change !== undefined && !p.hold_allowed && p.expected_change > 0.05)
        return `Forecast ${pct(p.expected_change, 0, true)} in ${p.horizon} days, but forecasts have not proven better than 'no change' yet.`;
      return r.my_sales_per_day ? `About ${perDay(r.my_sales_per_day)} sell per day; no rise worth waiting for.` : "Sell now.";
  }
}

function combine(items: InventoryItem[], names: Record<string, string>, gradualDays: number, byChar: boolean): Row[] {
  if (byChar) {
    return items.map((i) => ({ ...i, who: [names[i.char_key] ?? i.char_key], advice: (i.plan?.advice ?? "none") as AdviceKind }));
  }
  const by = new Map<number, Row>();
  for (const it of items) {
    const r = by.get(it.item_id);
    if (!r) {
      by.set(it.item_id, { ...it, who: [names[it.char_key] ?? it.char_key], advice: (it.plan?.advice ?? "none") as AdviceKind });
      continue;
    }
    r.bags += it.bags; r.bank += it.bank; r.count += it.count; r.bound += it.bound; r.value += it.value;
    r.who.push(names[it.char_key] ?? it.char_key);
    if (r.advice === "bound" && it.plan?.advice && it.plan.advice !== "bound") r.advice = it.plan.advice as AdviceKind;
  }
  // Selling gradually depends on how much you hold across all characters.
  for (const r of by.values()) {
    const tradable = r.count - r.bound;
    r.days_to_sell = r.my_sales_per_day && tradable > 0 ? tradable / r.my_sales_per_day : null;
    if (r.advice === "sell" || r.advice === "gradual")
      r.advice = r.days_to_sell !== null && r.days_to_sell > gradualDays ? "gradual" : "sell";
  }
  return [...by.values()];
}

export default function SellPlan() {
  const { version } = useApp();
  const { data, error } = useData(api.inventory, [], version);
  const [f, setF] = useStored("sellplan.filters", { char: "", advice: "", search: "" });
  const [sorting, setSorting] = useStored("sellplan.sort", [{ id: "advice", desc: false }]);
  const navigate = useNavigate();

  const names = useMemo(() => Object.fromEntries((data?.characters ?? []).map((c) => [c.char_key, c.name ?? c.char_key])), [data]);
  const gradualDays = data?.advice.gradual_days ?? 3;
  const all = useMemo(() => data
    ? combine(data.items.filter((i) => !f.char || i.char_key === f.char), names, gradualDays, false) : [], [data, f.char, names, gradualDays]);
  const rows = useMemo(() => {
    const q = f.search.trim().toLowerCase();
    return all.filter((r) => (!f.advice || r.advice === f.advice) && (!q || r.name.toLowerCase().includes(q)));
  }, [all, f.advice, f.search]);

  const summary = useMemo(() => {
    const s: Partial<Record<AdviceKind, { n: number; value: number }>> = {};
    for (const r of all) {
      const e = (s[r.advice] ??= { n: 0, value: 0 });
      e.n += 1;
      e.value += r.value;
    }
    return s;
  }, [all]);

  const columns = useMemo<ColumnDef<Row, unknown>[]>(() => [
    { id: "name", header: "Item", accessorFn: (r) => r.name, meta: { align: "left", csv: (r: Row) => r.name },
      cell: ({ row }) => (
        <span className="item-name">
          <ItemIcon id={row.original.icon_id} quality={row.original.quality} />
          <ItemName name={row.original.name} quality={row.original.quality} />
        </span>
      ) },
    { id: "advice", header: "Do this", accessorFn: (r) => ADVICE[r.advice].order,
      meta: { align: "left", hint: "What to do with this item today.", csv: (r: Row) => ADVICE[r.advice].label },
      cell: ({ row }) => (
        <Hint text={ADVICE[row.original.advice].hint} plain>
          <span className={`badge advice-${row.original.advice}`}>{ADVICE[row.original.advice].label}</span>
        </Hint>
      ) },
    { id: "why", header: "Why", enableSorting: false, accessorFn: (r) => why(r, gradualDays),
      meta: { align: "left", csv: (r: Row) => why(r, gradualDays) },
      cell: ({ row }) => <span className="small muted why">{why(row.original, gradualDays)}</span> },
    { id: "count", header: "Have", accessorFn: (r) => r.count, meta: { csv: (r: Row) => r.count },
      cell: ({ row }) => num(row.original.count, 0) },
    { id: "unit_ah", header: "AH, you keep", accessorFn: (r) => r.unit_ah,
      meta: { hint: "What one auction sale leaves you today, after the cut.", csv: (r: Row) => r.unit_ah },
      cell: ({ row }) => <Money value={row.original.unit_ah} /> },
    { id: "vendor_sell", header: "Vendor", accessorFn: (r) => r.vendor_sell, meta: { csv: (r: Row) => r.vendor_sell },
      cell: ({ row }) => <Money value={row.original.vendor_sell} /> },
    { id: "value", header: "Worth", accessorFn: (r) => r.value,
      meta: { hint: "Everything you hold, each unit sold where it fetches more.", csv: (r: Row) => Math.round(r.value) },
      cell: ({ row }) => <b><Money value={row.original.value} /></b> },
    { id: "expected", header: "Next days", accessorFn: (r) => r.plan?.expected_change ?? -99,
      meta: { hint: "Forecast price change over the advice horizon, with its 80% range. Shown for reference; it only becomes 'Hold' when forecasts have proven themselves.",
        csv: (r: Row) => r.plan?.expected_change },
      cell: ({ row }) => {
        const p = row.original.plan;
        if (p?.expected_change === null || p?.expected_change === undefined) return <span className="muted">-</span>;
        return (
          <Hint text={`80% range ${pct(p.low, 0, true)} to ${pct(p.high, 0, true)}; ${pct(p.p_up)} chance of a rise.`} plain>
            <span className={p.expected_change >= 0 ? "pos" : "neg"}>{pct(p.expected_change, 1, true)}</span>
          </Hint>
        );
      } },
    { id: "days_to_sell", header: "Days to sell", accessorFn: (r) => r.days_to_sell ?? Infinity,
      meta: { hint: "How long selling all of it takes at your expected sales per day.", csv: (r: Row) => r.days_to_sell },
      cell: ({ row }) => num(row.original.days_to_sell) },
    { id: "who", header: "Character", enableSorting: false, accessorFn: (r) => r.who.join(", "),
      meta: { align: "left", csv: (r: Row) => r.who.join("; ") },
      cell: ({ row }) => <span className="muted small">{row.original.who.join(", ")}</span> },
  ], [gradualDays]);

  const set = (k: string, v: unknown) => setF((old) => ({ ...old, [k]: v }));

  if (error) return <div className="error-banner">{error}</div>;
  if (!data) return <Skeleton />;
  const bt = data.advice.backtest;

  return (
    <section>
      <div className="page-head">
        <h1>Sell plan</h1>
        <p className="lead">
          What to do with everything your characters hold: sell it on the auction house now, sell it a few at a time,
          take it to a vendor, or hold it because the price is expected to rise. Listing deposits are not counted.
        </p>
      </div>

      <div className={`warning ${data.advice.hold_allowed ? "" : "info"}`} style={{ marginBottom: 18 }}>
        {data.advice.hold_allowed ? (
          <span>
            <b>Hold advice is on.</b> The {data.advice.horizon_days}-day forecasts beat "no change" in the backtest
            (typical error {pct(bt?.mae_model ? Math.expm1(bt.mae_model) : null, 1)} against {pct(bt?.mae_naive ? Math.expm1(bt.mae_naive) : null, 1)},
            p = {num(bt?.p_value, 3)}). <Link to="/accuracy">How accurate are they?</Link>
          </span>
        ) : (
          <span>
            <b>Simsar does not advise holding yet.</b>{" "}
            {bt?.ok
              ? <>The {data.advice.horizon_days}-day forecasts have not beaten "no change" in the backtest (skill {pct(bt.skill, 1)}{bt.p_value !== null && bt.p_value !== undefined ? `, p = ${num(bt.p_value, 2)}` : ""}), so waiting for a better price is a guess.</>
              : <>Checking the {data.advice.horizon_days}-day forecasts needs {bt?.needs ?? "more price history"}.</>}
            {" "}Until they prove themselves, the advice is sell now, sell gradually or vendor. <Link to="/accuracy">Forecast accuracy</Link>
          </span>
        )}
      </div>

      {data.characters.length === 0 ? (
        <div className="card empty-state">
          <h3>No characters yet</h3>
          <p>Log in with the Simsar Forever addon enabled, open your bags and your bank, then type <code>/reload</code>.</p>
        </div>
      ) : (
        <>
          <div className="tiles">
            {(["hold", "sell", "gradual", "vendor"] as AdviceKind[]).map((k) => (
              <button key={k} className={`tile tile-button ${f.advice === k ? "selected" : ""}`}
                onClick={() => set("advice", f.advice === k ? "" : k)}>
                <div className="tile-title"><span className={`advice-${k}`}>{ADVICE[k].label}</span></div>
                <div className="tile-value">{summary[k]?.n ?? 0} <span className="tile-sub">items</span></div>
                <div className="tile-sub"><Money value={summary[k]?.value ?? 0} /></div>
              </button>
            ))}
          </div>

          <div className="filters">
            <select value={f.char} onChange={(e) => set("char", e.target.value)}>
              <option value="">All characters</option>
              {data.characters.map((c) => (
                <option key={c.char_key} value={c.char_key} style={{ color: CLASS_COLORS[c.class ?? ""] }}>{c.name}</option>
              ))}
            </select>
            <select value={f.advice} onChange={(e) => set("advice", e.target.value)}>
              <option value="">Every advice</option>
              {Object.entries(ADVICE).map(([k, a]) => <option key={k} value={k}>{a.label}</option>)}
            </select>
            <input placeholder="Search items" value={f.search} onChange={(e) => set("search", e.target.value)} />
            <span className="spacer" />
            <span className="small">{rows.length} items</span>
            <button onClick={() => downloadCsv("simsar-forever-sell-plan", rows, columns)}>Export CSV</button>
          </div>

          <DataTable rows={rows} columns={columns} sorting={sorting} onSortingChange={setSorting}
            onRowClick={(r) => navigate(`/item/${r.item_id}`)} empty="Nothing matches these filters." />
        </>
      )}
    </section>
  );
}

export type { Plan };
