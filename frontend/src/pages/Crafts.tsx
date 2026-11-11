import type { ColumnDef } from "@tanstack/react-table";
import { useMemo } from "react";
import { Link } from "react-router-dom";
import { type Craft, type Verdict, api } from "../api";
import { Flags, VerdictBadge } from "../components/Badges";
import { DataTable, downloadCsv } from "../components/DataTable";
import { Hint } from "../components/Hint";
import { useApp } from "../context";
import { Money, num, pct } from "../format";
import { useData, useStored } from "../hooks";
import { CRAFT_COLUMNS, VERDICTS } from "../strings";

function col(key: string, cell: (c: Craft) => JSX.Element | string, csv: (c: Craft) => string | number | null | undefined,
  value?: (c: Craft) => number | null | undefined): ColumnDef<Craft, unknown> {
  const info = CRAFT_COLUMNS[key];
  return {
    id: key,
    header: info.title,
    accessorFn: (c) => (value ? value(c) : (c as unknown as Record<string, unknown>)[key]),
    sortingFn: (a, b) => {
      const x = (value ? value(a.original) : (a.original as unknown as Record<string, number | null>)[key]) ?? -Infinity;
      const y = (value ? value(b.original) : (b.original as unknown as Record<string, number | null>)[key]) ?? -Infinity;
      return (x as number) - (y as number);
    },
    meta: { hint: info.hint, csv },
    cell: ({ row }) => cell(row.original),
  };
}

const money = (key: keyof Craft, signed = false) =>
  col(key, (c) => <Money value={c[key] as number | null} signed={signed} />, (c) => c[key] as number | null);

function Breakdown({ c }: { c: Craft }) {
  return (
    <div className="breakdown">
      <table className="mini">
        <thead>
          <tr><th className="left">Material</th><th>Count</th><th>Buy price</th><th>Sells for (net)</th><th>Line cost</th></tr>
        </thead>
        <tbody>
          {c.reagents.map((r) => (
            <tr key={`${r.item_id}-${r.name}`}>
              <td className="left">{r.item_id ? <Link to={`/item/${r.item_id}`}>{r.name}</Link> : r.name}</td>
              <td>{num(r.count, 0)}</td>
              <td><Money value={r.unit_price} />{r.price_src === "vendor" && <span className="muted small"> vendor</span>}</td>
              <td><Money value={r.unit_net_sell} /></td>
              <td><Money value={r.unit_price !== null ? r.unit_price * r.count : null} /></td>
            </tr>
          ))}
        </tbody>
      </table>
      <div className="breakdown-side">
        <div>
          Makes <b>{num(c.yield, c.yield % 1 ? 1 : 0)}</b> x{" "}
          {c.product_id ? <Link to={`/item/${c.product_id}`}>{c.product_name}</Link> : c.product_name}
          {c.product_price !== null && <> selling at <Money value={c.product_price} /></>}
        </div>
        {c.missing.length > 0 && <div className="neg">No price for: {c.missing.join(", ")}</div>}
        {c.recipe_item && (
          <div>
            Recipe on AH: <Link to={`/item/${c.recipe_item.item_id}`}>{c.recipe_item.name}</Link>{" "}
            <Money value={c.recipe_item.price} />
            {c.payback_days !== undefined && <> - pays back in about {num(c.payback_days, 1)} days</>}
          </div>
        )}
        <div className="muted small">Source: {c.source}{c.learned === 0 ? " (not learned yet)" : ""}</div>
        <Flags flags={c.product_flags} />
      </div>
    </div>
  );
}

export default function Crafts() {
  const { version, status } = useApp();
  const { data } = useData(api.crafts, [], version);
  const [f, setF] = useStored("crafts.filters", { profession: "", verdict: "", learnedOnly: false, search: "" });
  const [sorting, setSorting] = useStored("crafts.sort", [{ id: "profit_day", desc: true }]);

  const professions = useMemo(() => [...new Set((data ?? []).map((c) => c.profession))].sort(), [data]);
  const rows = useMemo(() => {
    const q = f.search.trim().toLowerCase();
    return (data ?? []).filter((c) =>
      (!f.profession || c.profession === f.profession) &&
      (!f.verdict || c.verdict === f.verdict) &&
      (!f.learnedOnly || c.learned !== 0) &&
      (!q || c.name.toLowerCase().includes(q) || c.reagents.some((r) => r.name.toLowerCase().includes(q))));
  }, [data, f]);

  const columns = useMemo<ColumnDef<Craft, unknown>[]>(() => [
    col("name", (c) => (
      <span className={c.learned === 0 ? "muted" : ""}>
        {c.name}
        <span className="muted small"> {c.profession}</span>
      </span>
    ), (c) => c.name, () => null),
    col("verdict", (c) => <VerdictBadge verdict={c.verdict} />, (c) => VERDICTS[c.verdict], () => null),
    money("cost_buy"),
    money("mats_value"),
    money("revenue"),
    money("profit", true),
    money("profit_vs_mats", true),
    col("roi", (c) => <span className={(c.roi ?? 0) < 0 ? "neg" : "pos"}>{pct(c.roi, 0, true)}</span>, (c) => c.roi),
    col("product_sales_per_day", (c) => num(c.product_sales_per_day), (c) => c.product_sales_per_day),
    money("profit_day"),
    col("payback_days", (c) => (c.payback_days !== undefined ? `${num(c.payback_days, 1)} d` : "-"),
      (c) => c.payback_days, (c) => c.payback_days),
  ], []);

  const set = (k: string, v: unknown) => setF((old) => ({ ...old, [k]: v }));

  return (
    <section>
      <div className="page-head">
        <h1>Crafts</h1>
        <p className="lead">
          Every known recipe priced at today's market. <b>Profit</b> assumes you buy all materials;
          <b> vs selling mats</b> compares crafting with simply selling the materials you already have. Click a row for
          the material breakdown.
          <Hint text="Each material is priced at the cheaper of the auction house and a vendor. Vendor prices are recorded by the SimsarForeverExport addon whenever you open a vendor window." />
        </p>
      </div>
      {data && !data.length && (
        <div className="card empty-state">
          <h3>No recipes yet</h3>
          <p>
            {status?.demo ? "The demo has no recipes." : <>Install the <b>SimsarForeverExport</b> addon (see README), open each
            profession window and the profession trainer in game, then type <code>/reload</code>. Simsar Forever picks the file
            up within seconds. You can also add recipes by hand in <code>recipes.yaml</code>.</>}
          </p>
        </div>
      )}
      <div className="filters">
        <select value={f.profession} onChange={(e) => set("profession", e.target.value)}>
          <option value="">All professions</option>
          {professions.map((p) => <option key={p}>{p}</option>)}
        </select>
        <select value={f.verdict} onChange={(e) => set("verdict", e.target.value)}>
          <option value="">Any verdict</option>
          {(Object.keys(VERDICTS) as Verdict[]).map((v) => <option key={v} value={v}>{VERDICTS[v]}</option>)}
        </select>
        <input placeholder="Search recipe or material" value={f.search} onChange={(e) => set("search", e.target.value)} />
        <label className="check">
          <input type="checkbox" checked={f.learnedOnly} onChange={(e) => set("learnedOnly", e.target.checked)} />
          Only recipes I know
        </label>
        <span className="spacer" />
        <button onClick={() => downloadCsv("simsar-forever-crafts", rows, columns)}>Export CSV</button>
      </div>
      {!data ? <div className="loading">Loading...</div> : (
        <DataTable rows={rows} columns={columns} sorting={sorting} onSortingChange={setSorting}
          expand={(c) => <Breakdown c={c} />} rowClass={(c) => `verdict-row-${c.verdict}`} />
      )}
    </section>
  );
}
