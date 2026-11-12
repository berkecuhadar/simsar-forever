import { useMemo } from "react";
import { Skeleton } from "../components/Feedback";
import { useNavigate } from "react-router-dom";
import { api } from "../api";
import { Chart, THEME, axisStyle, baseOption } from "../components/Chart";
import { DataTable, downloadCsv } from "../components/DataTable";
import { useApp } from "../context";
import { moneyText } from "../format";
import { useData, useStored } from "../hooks";
import { itemColumns } from "./itemColumns";

const KEYS = ["name", "price_now", "sell_price", "net_sell", "sale_rate", "my_sales_per_day", "income_day",
  "available", "trend", "volatility", "disc_ref", "flags"] as const;

export default function Gathering() {
  const { groups, version } = useApp();
  const gather = [...groups.filter((g) => g.role === "gather"), ...groups.filter((g) => g.role === "craft")];
  const [state, setState] = useStored("gathering", { group: "skinning" });
  const [sorting, setSorting] = useStored("gathering.sort", [{ id: "income_day", desc: true }]);
  const { data } = useData(() => api.items("tracked"), [], version);
  const navigate = useNavigate();

  const rows = useMemo(() => (data ?? []).filter((i) => i.groups.includes(state.group)), [data, state.group]);
  const columns = useMemo(() => itemColumns([...KEYS], groups), [groups]);
  const top = useMemo(() => [...rows].filter((r) => r.income_day).sort((a, b) => b.income_day! - a.income_day!)
    .slice(0, 15).reverse(), [rows]);

  const option = useMemo(() => ({
    ...baseOption,
    grid: { left: 180, right: 30, top: 10, bottom: 30 },
    tooltip: { ...baseOption.tooltip, trigger: "item",
      formatter: (p: { name: string; value: number }) => `${p.name}<br/>${moneyText(p.value)} per day` },
    xAxis: { type: "value", ...axisStyle({ axisLabel: { color: THEME.muted, formatter: (v: number) => moneyText(v) } }) },
    yAxis: { type: "category", data: top.map((r) => r.name), ...axisStyle({ splitLine: { show: false } }) },
    series: [{ type: "bar", data: top.map((r) => ({ value: r.income_day, itemId: r.item_id })),
      itemStyle: { color: groups.find((g) => g.key === state.group)?.color ?? THEME.gold, borderRadius: [0, 4, 4, 0] } }],
  }), [top, groups, state.group]);

  return (
    <section>
      <div className="page-head">
        <h1>What to sell</h1>
        <p className="lead">
          For things you gather or craft yourself, the question is not "is it cheap" but "what is a unit worth after
          fees, and how many can the market take per day". Gathering professions come first. <b>Income/day</b> is the most you can expect to earn from one
          item per day if you keep it listed at a competitive price.
        </p>
      </div>
      <div className="tabs">
        {gather.map((g) => (
          <button key={g.key} className={state.group === g.key ? "active" : ""} onClick={() => setState({ group: g.key })}>
            <span className="swatch" style={{ background: g.color }} />{g.title}
          </button>
        ))}
        <span className="spacer" />
        <button onClick={() => downloadCsv(`simsar-forever-${state.group}`, rows, columns)}>Export CSV</button>
      </div>
      {top.length > 0 && (
        <div className="card">
          <h3>Best sellers by income per day</h3>
          <Chart option={option as never} height={Math.max(220, top.length * 24 + 40)}
            onClick={(p) => navigate(`/item/${(p.data as { itemId: number }).itemId}`)} />
        </div>
      )}
      {!data ? <Skeleton /> : (
        <DataTable rows={rows} columns={columns} sorting={sorting} onSortingChange={setSorting}
          onRowClick={(r) => navigate(`/item/${r.item_id}`)} />
      )}
    </section>
  );
}
