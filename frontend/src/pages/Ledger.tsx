import type { ColumnDef } from "@tanstack/react-table";
import { useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { type AuctionItem, type LedgerData, api } from "../api";
import { Chart, THEME, axisStyle, baseOption } from "../components/Chart";
import { DataTable, downloadCsv } from "../components/DataTable";
import { Skeleton } from "../components/Feedback";
import { Hint } from "../components/Hint";
import { ItemIcon, ItemName } from "../components/Icons";
import { useApp } from "../context";
import { Money, dateTime, moneyText, num, pct } from "../format";
import { useData, useStored } from "../hooks";
import { CLASS_COLORS } from "./Inventory";

// Days are stored as YYYYMMDD in the game's local time.
function toDay(d: Date) {
  return d.getFullYear() * 10000 + (d.getMonth() + 1) * 100 + d.getDate();
}
function fromDay(day: number) {
  return new Date(Math.floor(day / 10000), Math.floor(day / 100) % 100 - 1, day % 100);
}
function addDays(d: Date, n: number) {
  const out = new Date(d);
  out.setDate(out.getDate() + n);
  return out;
}
function dayLabel(day: number) {
  return fromDay(day).toLocaleDateString(undefined, { day: "numeric", month: "short" });
}

const PERIODS = [
  ["today", "Today"], ["yesterday", "Yesterday"], ["week", "This week"], ["last_week", "Last week"],
  ["month", "This month"], ["last_month", "Last month"], ["year", "This year"], ["all", "All time"],
] as const;
type Period = (typeof PERIODS)[number][0];

function range(period: Period, now = new Date()): [number, number] {
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const monday = addDays(today, -((today.getDay() + 6) % 7));
  switch (period) {
    case "today": return [toDay(today), toDay(today)];
    case "yesterday": return [toDay(addDays(today, -1)), toDay(addDays(today, -1))];
    case "week": return [toDay(monday), toDay(today)];
    case "last_week": return [toDay(addDays(monday, -7)), toDay(addDays(monday, -1))];
    case "month": return [toDay(new Date(today.getFullYear(), today.getMonth(), 1)), toDay(today)];
    case "last_month": return [toDay(new Date(today.getFullYear(), today.getMonth() - 1, 1)),
      toDay(new Date(today.getFullYear(), today.getMonth(), 0))];
    case "year": return [toDay(new Date(today.getFullYear(), 0, 1)), toDay(today)];
    default: return [0, 99999999];
  }
}

const KIND_ORDER = ["trade", "earn", "cost", "other", "transfer"];
const KIND_TITLES: Record<string, string> = {
  trade: "Trading", earn: "Earned in the world", cost: "Running costs", other: "Other", transfer: "Not income or spending",
};

export default function Ledger() {
  const { version } = useApp();
  const { data, error } = useData(api.ledger, [], version);
  const [f, setF] = useStored("ledger.filters", { char: "", period: "week" as Period });
  const [auctionSort, setAuctionSort] = useStored("ledger.auction.sort", [{ id: "net", desc: true }]);
  const [txSort, setTxSort] = useStored("ledger.tx.sort", [{ id: "t", desc: true }]);
  const navigate = useNavigate();

  const names = useMemo(() => Object.fromEntries((data?.characters ?? []).map((c) => [c.char_key, c.name ?? c.char_key])),
    [data]);
  const [from, to] = range(f.period);
  const inChar = (key: string) => !f.char || key === f.char;

  const totals = useMemo(() => {
    const byCat: Record<string, { income: number; expense: number; n: number }> = {};
    for (const r of data?.days ?? []) {
      if (!inChar(r.char_key) || r.day < from || r.day > to) continue;
      const e = (byCat[r.category] ??= { income: 0, expense: 0, n: 0 });
      e.income += r.income;
      e.expense += r.expense;
      e.n += r.n;
    }
    return byCat;
  }, [data, f.char, from, to]); // eslint-disable-line react-hooks/exhaustive-deps

  const cats = data?.categories ?? {};
  const kindOf = (c: string) => cats[c]?.kind ?? "other";
  const sum = (pred: (c: string) => boolean, field: "income" | "expense") =>
    Object.entries(totals).filter(([c]) => pred(c)).reduce((s, [, e]) => s + e[field], 0);
  const income = sum((c) => kindOf(c) !== "transfer", "income");
  const spent = sum((c) => kindOf(c) !== "transfer", "expense");
  const auction = ["AH_SALE", "AH_BUY", "AH_DEPOSIT", "AH"].reduce(
    (s, c) => s + (totals[c]?.income ?? 0) - (totals[c]?.expense ?? 0), 0);
  const goldNow = (data?.characters ?? []).filter((c) => inChar(c.char_key)).reduce((s, c) => s + (c.money ?? 0), 0);

  // Daily net for the chart: the selected period, or the last 30 days for today/yesterday.
  const daily = useMemo(() => {
    if (!data) return { days: [] as number[], net: [] as number[], gold: [] as (number | null)[] };
    const [a] = f.period === "today" || f.period === "yesterday" ? range("month") : [from];
    const known = data.days.map((r) => r.day);
    const start = a === 0 ? Math.min(...known, toDay(new Date())) : a;
    const days: number[] = [];
    for (let d = fromDay(start); toDay(d) <= Math.min(to, toDay(new Date())); d = addDays(d, 1)) days.push(toDay(d));
    const net = Object.fromEntries(days.map((d) => [d, 0]));
    for (const r of data.days) {
      if (inChar(r.char_key) && r.day in net && kindOf(r.category) !== "transfer") net[r.day] += r.income - r.expense;
    }
    return { days, net: days.map((d) => net[d]), gold: goldSeries(data, days, f.char) };
  }, [data, f.char, f.period, from, to]); // eslint-disable-line react-hooks/exhaustive-deps

  const chart = useMemo(() => ({
    ...baseOption,
    grid: { left: 70, right: 70, top: 36, bottom: 40 },
    tooltip: { ...baseOption.tooltip, valueFormatter: (v: number) => moneyText(v) },
    legend: { ...baseOption.legend, data: ["Net per day", "Gold on hand"] },
    xAxis: { type: "category", data: daily.days.map(dayLabel), ...axisStyle({ splitLine: { show: false } }) },
    yAxis: [
      { type: "value", ...axisStyle({ axisLabel: { color: THEME.muted, formatter: (v: number) => moneyText(v) } }) },
      { type: "value", ...axisStyle({ splitLine: { show: false }, axisLabel: { color: THEME.muted, formatter: (v: number) => moneyText(v) } }) },
    ],
    series: [
      { name: "Net per day", type: "bar", data: daily.net.map((v) => ({ value: v, itemStyle: { color: v < 0 ? THEME.red : THEME.green } })),
        itemStyle: { color: THEME.green, borderRadius: 3 } },
      { name: "Gold on hand", type: "line", yAxisIndex: 1, data: daily.gold, connectNulls: true, symbol: "none",
        lineStyle: { color: THEME.gold, width: 2 }, itemStyle: { color: THEME.gold } },
    ],
  }), [daily]);

  const history = useMemo(() => (data ? goldHistory(data, f.char, names) : null), [data, f.char, names]);

  const auctionRows = useMemo(() => data?.auction_items ?? [], [data]);
  const auctionColumns = useMemo<ColumnDef<AuctionItem, unknown>[]>(() => [
    { id: "name", header: "Item", accessorFn: (r) => r.name, meta: { align: "left", csv: (r: AuctionItem) => r.name },
      cell: ({ row }) => (
        <span className="item-name">
          <ItemIcon id={row.original.icon_id} quality={row.original.quality} />
          <ItemName name={row.original.name} quality={row.original.quality} />
        </span>
      ) },
    { id: "sold", header: "Sold", accessorFn: (r) => r.sold, meta: { csv: (r: AuctionItem) => r.sold },
      cell: ({ row }) => row.original.sold ? num(row.original.sold, 0) : <span className="muted">-</span> },
    { id: "net", header: "Received", accessorFn: (r) => r.net,
      meta: { hint: "What the sale mails paid you, after the auction house cut.", csv: (r: AuctionItem) => r.net },
      cell: ({ row }) => <Money value={row.original.net || null} /> },
    { id: "avg_sale", header: "Each", accessorFn: (r) => r.avg_sale,
      meta: { hint: "Average received per unit sold, after the cut.", csv: (r: AuctionItem) => r.avg_sale },
      cell: ({ row }) => <Money value={row.original.avg_sale} /> },
    { id: "cut", header: "AH cut", accessorFn: (r) => r.cut, meta: { csv: (r: AuctionItem) => r.cut },
      cell: ({ row }) => <Money value={row.original.cut || null} /> },
    { id: "bought", header: "Bought", accessorFn: (r) => r.bought, meta: { csv: (r: AuctionItem) => r.bought },
      cell: ({ row }) => row.original.bought ? num(row.original.bought, 0) : <span className="muted">-</span> },
    { id: "spent", header: "Paid", accessorFn: (r) => r.spent,
      meta: { hint: "What you paid for this item on the auction house (from 'auction won' mails).", csv: (r: AuctionItem) => r.spent },
      cell: ({ row }) => <Money value={row.original.spent || null} /> },
    { id: "margin", header: "Received - paid", accessorFn: (r) => r.margin,
      meta: { hint: "Received from sales minus paid for purchases of the same item. For flips this is the profit; for items you craft or gather the materials cost is not in it.", csv: (r: AuctionItem) => r.margin },
      cell: ({ row }) => <Money value={row.original.margin} signed /> },
    { id: "expired", header: "Expired", accessorFn: (r) => r.expired + r.cancelled,
      meta: { hint: "Auctions that came back unsold (expired) or that you cancelled.", csv: (r: AuctionItem) => r.expired + r.cancelled },
      cell: ({ row }) => num(row.original.expired + row.original.cancelled, 0) },
    { id: "sell_through", header: "Sell-through", accessorFn: (r) => r.sell_through ?? -1,
      meta: { hint: "Share of your auctions of this item that sold. Counted from your mail since the addon started recording.", csv: (r: AuctionItem) => r.sell_through },
      cell: ({ row }) => pct(row.original.sell_through) },
  ], []);

  type Tx = LedgerData["transactions"][number];
  const txRows = useMemo(() => (data?.transactions ?? []).filter((t) => {
    const day = toDay(new Date(t.t * 1000));
    return inChar(t.char_key) && day >= from && day <= to;
  }), [data, f.char, from, to]); // eslint-disable-line react-hooks/exhaustive-deps
  const txColumns = useMemo<ColumnDef<Tx, unknown>[]>(() => [
    { id: "t", header: "When", accessorFn: (r) => r.t, meta: { align: "left", csv: (r: Tx) => new Date(r.t * 1000).toISOString() },
      cell: ({ row }) => dateTime(row.original.t) },
    { id: "char", header: "Character", accessorFn: (r) => names[r.char_key] ?? r.char_key,
      meta: { align: "left", csv: (r: Tx) => names[r.char_key] ?? r.char_key } },
    { id: "category", header: "Category", accessorFn: (r) => cats[r.category]?.label ?? r.category,
      meta: { align: "left", csv: (r: Tx) => r.category } },
    { id: "amount", header: "Amount", accessorFn: (r) => r.amount, meta: { csv: (r: Tx) => r.amount },
      cell: ({ row }) => <Money value={row.original.amount} signed /> },
    { id: "zone", header: "Where", accessorFn: (r) => r.zone ?? "", meta: { align: "left", csv: (r: Tx) => r.zone },
      cell: ({ row }) => <span className="muted small">{row.original.zone ?? ""}</span> },
  ], [names, cats]);

  const set = (k: string, v: unknown) => setF((old) => ({ ...old, [k]: v }));

  if (error) return <div className="error-banner">{error}</div>;
  if (!data) return <Skeleton />;

  const empty = data.days.length === 0 && Object.keys(data.balances).length === 0;
  const rows = Object.entries(totals).sort(([a], [b]) =>
    KIND_ORDER.indexOf(kindOf(a)) - KIND_ORDER.indexOf(kindOf(b)) || (totals[b].income + totals[b].expense) - (totals[a].income + totals[a].expense));

  return (
    <section>
      <div className="page-head">
        <h1>Gold ledger</h1>
        <p className="lead">
          Where your gold came from and where it went, per character and category. The addon books every change of gold
          under what you were doing at that moment: an auction mail, a vendor window, a flight, a repair.
          {data.sources.includes("accountant") && data.simsar_since && (
            <> Days before {dayLabel(data.simsar_since)} come from Accountant Classic.</>
          )}
        </p>
      </div>

      {empty ? (
        <div className="card empty-state">
          <h3>No gold history yet</h3>
          <p>Install or update the Simsar Forever addon (Settings), play as usual, then type <code>/reload</code>.
            If you use Accountant Classic, its history is imported automatically.</p>
        </div>
      ) : (
        <>
          <div className="char-grid">
            <button className={`char-card ${!f.char ? "selected" : ""}`} onClick={() => set("char", "")}>
              <div className="char-name">All characters</div>
              <div className="char-value"><Money value={data.characters.reduce((s, c) => s + (c.money ?? 0), 0)} /></div>
              <div className="muted small">gold on hand</div>
            </button>
            {data.characters.map((c) => (
              <button key={c.char_key} className={`char-card ${f.char === c.char_key ? "selected" : ""}`}
                onClick={() => set("char", f.char === c.char_key ? "" : c.char_key)}>
                <div className="char-name" style={{ color: CLASS_COLORS[c.class ?? ""] }}>{c.name}</div>
                <div className="char-value"><Money value={c.money ?? 0} /></div>
                <div className="muted small">gold on hand</div>
              </button>
            ))}
          </div>

          <div className="tabs">
            {PERIODS.map(([key, label]) => (
              <button key={key} className={f.period === key ? "active" : ""} onClick={() => set("period", key)}>{label}</button>
            ))}
          </div>

          <div className="tiles">
            <div className="tile">
              <div className="tile-title">Income</div>
              <div className="tile-value"><Money value={income} /></div>
            </div>
            <div className="tile">
              <div className="tile-title">Spent</div>
              <div className="tile-value"><Money value={spent} /></div>
            </div>
            <div className="tile">
              <div className="tile-title">Net <Hint text="Income minus spending. Gold moved between your own characters is left out." /></div>
              <div className="tile-value"><Money value={income - spent} signed /></div>
            </div>
            <div className="tile">
              <div className="tile-title">Auction house net <Hint text="Auction sales minus auction purchases, deposits and other auction house payments in this period." /></div>
              <div className="tile-value"><Money value={auction} signed /></div>
            </div>
          </div>

          <div className="breakdown">
            <div className="card">
              <h3>By category</h3>
              {rows.length === 0 ? <p className="muted">No gold moved in this period.</p> : (
                <table className="mini" style={{ width: "100%" }}>
                  <thead>
                    <tr><th className="left">Category</th><th>Income</th><th>Spent</th><th>Net</th><th>Times</th></tr>
                  </thead>
                  <tbody>
                    {rows.map(([c, e], i) => {
                      const kind = kindOf(c);
                      const first = i === 0 || kindOf(rows[i - 1][0]) !== kind;
                      return (
                        <FragmentRow key={c} title={first ? KIND_TITLES[kind] : null}>
                          <td className="left">{cats[c]?.label ?? c}</td>
                          <td><Money value={e.income || null} /></td>
                          <td><Money value={e.expense || null} /></td>
                          <td><Money value={e.income - e.expense} signed /></td>
                          <td className="muted">{e.n}</td>
                        </FragmentRow>
                      );
                    })}
                    <tr>
                      <td className="left"><b>Total</b> <span className="muted small">without transfers</span></td>
                      <td><b><Money value={income} /></b></td>
                      <td><b><Money value={spent} /></b></td>
                      <td><b><Money value={income - spent} signed /></b></td>
                      <td />
                    </tr>
                  </tbody>
                </table>
              )}
            </div>
            <div className="card">
              <h3>Day by day</h3>
              <Chart option={chart} height={300} />
            </div>
          </div>

          {history && history.days.length > 1 && (
            <div className="card">
              <h3>Gold over time <Hint text="Gold on hand at the end of each day. Days without a record carry the last known amount. Today uses the latest bag scan." /></h3>
              <Chart option={history.option} height={300} />
              <p className="muted small">
                Now <Money value={goldNow} />
                {history.change !== null && <> · <Money value={history.change} signed /> since {dayLabel(history.days[0])}</>}
              </p>
            </div>
          )}

          <h2 className="section-title">
            Auction house, item by item <Hint text="From your auction mail: sale invoices, 'auction won' mails and expired or cancelled auctions. Covers all characters and all time." />
          </h2>
          <div className="filters">
            <span className="spacer" />
            <button onClick={() => downloadCsv("simsar-forever-auction-items", auctionRows, auctionColumns)}>Export CSV</button>
          </div>
          <DataTable rows={auctionRows} columns={auctionColumns} sorting={auctionSort} onSortingChange={setAuctionSort}
            onRowClick={(r) => r.item_id && navigate(`/item/${r.item_id}`)} pageSize={20}
            empty="No auction mail recorded yet. Open your mailbox in game with the addon installed, then /reload." />

          <h2 className="section-title">Gold movements</h2>
          <div className="filters">
            <span className="muted small">{txRows.length} in this period{f.char ? ` for ${names[f.char]}` : ""}. The addon keeps the last 90 days.</span>
            <span className="spacer" />
            <button onClick={() => downloadCsv("simsar-forever-gold", txRows, txColumns)}>Export CSV</button>
          </div>
          <DataTable rows={txRows} columns={txColumns} sorting={txSort} onSortingChange={setTxSort} pageSize={25}
            empty="No single gold movements in this period." />
        </>
      )}
    </section>
  );
}

function FragmentRow({ title, children }: { title: string | null; children: React.ReactNode }) {
  return (
    <>
      {title && <tr><td colSpan={5} className="left muted small" style={{ paddingTop: 14 }}>{title}</td></tr>}
      <tr>{children}</tr>
    </>
  );
}

function carried(balances: [number, number][], days: number[]) {
  const out: (number | null)[] = [];
  let i = 0;
  let last: number | null = null;
  for (const d of days) {
    while (i < balances.length && balances[i][0] <= d) last = balances[i++][1];
    out.push(last);
  }
  return out;
}

function goldSeries(data: LedgerData, days: number[], char: string) {
  const keys = data.characters.map((c) => c.char_key).filter((k) => !char || k === char);
  const per = keys.map((k) => carried(withToday(data, k), days));
  return days.map((_, i) => {
    const vals = per.map((p) => p[i]).filter((v): v is number => v !== null);
    return vals.length ? vals.reduce((s, v) => s + v, 0) : null;
  });
}

function withToday(data: LedgerData, key: string): [number, number][] {
  const list = [...(data.balances[key] ?? [])];
  const c = data.characters.find((x) => x.char_key === key);
  if (c?.money !== null && c?.money !== undefined && c.money_at) {
    const day = toDay(new Date(c.money_at * 1000));
    const at = list.findIndex(([d]) => d === day);
    if (at >= 0) list[at] = [day, c.money];
    else if (!list.length || list[list.length - 1][0] < day) list.push([day, c.money]);
  }
  return list;
}

function goldHistory(data: LedgerData, char: string, names: Record<string, string>) {
  const keys = data.characters.map((c) => c.char_key).filter((k) => !char || k === char);
  const all = keys.flatMap((k) => withToday(data, k).map(([d]) => d));
  if (!all.length) return null;
  const days: number[] = [];
  for (let d = fromDay(Math.min(...all)); toDay(d) <= Math.max(...all); d = addDays(d, 1)) days.push(toDay(d));
  const palette = [THEME.gold, THEME.blue, THEME.green, THEME.violet, THEME.teal, THEME.red];
  const series = keys.map((k, i) => {
    const c = data.characters.find((x) => x.char_key === k);
    return {
      name: names[k] ?? k, type: "line", stack: "gold", areaStyle: { opacity: 0.25 }, symbol: "none", connectNulls: true,
      data: carried(withToday(data, k), days),
      lineStyle: { width: 1.5 }, itemStyle: { color: CLASS_COLORS[c?.class ?? ""] ?? palette[i % palette.length] },
    };
  });
  const total = goldSeries(data, days, char);
  const firstTotal = total.find((v) => v !== null) ?? null;
  const lastTotal = total[total.length - 1];
  return {
    days,
    change: firstTotal !== null && lastTotal !== null ? lastTotal - firstTotal : null,
    option: {
      ...baseOption,
      grid: { left: 80, right: 24, top: 36, bottom: 40 },
      tooltip: { ...baseOption.tooltip, valueFormatter: (v: number) => moneyText(v) },
      xAxis: { type: "category", data: days.map(dayLabel), boundaryGap: false, ...axisStyle({ splitLine: { show: false } }) },
      yAxis: { type: "value", ...axisStyle({ axisLabel: { color: THEME.muted, formatter: (v: number) => moneyText(v) } }) },
      series,
    },
  };
}
