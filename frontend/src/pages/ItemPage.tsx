import { type ReactNode, useMemo } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { api } from "../api";
import { Flags, LabelBadge, VerdictBadge } from "../components/Badges";
import { Chart, THEME, axisStyle, baseOption } from "../components/Chart";
import { StatsCard } from "../components/StatsCard";
import { Hint } from "../components/Hint";
import { groupTitle, useApp } from "../context";
import { Money, ago, moneyText, num, pct } from "../format";
import { useData } from "../hooks";
import { COLUMNS, PRICE_SOURCES } from "../strings";

function Tile({ title, hint, children }: { title: string; hint?: string; children: ReactNode }) {
  return (
    <div className="tile">
      <div className="tile-title">{title}{hint && <Hint text={hint} />}</div>
      <div className="tile-value">{children}</div>
    </div>
  );
}

export default function ItemPage() {
  const { id } = useParams();
  const { groups, version } = useApp();
  const navigate = useNavigate();
  const { data, error } = useData(() => api.item(Number(id)), [id], version);
  const { data: stats } = useData(() => api.itemStats(Number(id)), [id], version);

  const priceOption = useMemo(() => {
    if (!data) return null;
    const h = data.history;
    const ms = (t: number) => t * 1000;
    return {
      ...baseOption,
      tooltip: { ...baseOption.tooltip, valueFormatter: (v: number) => moneyText(v) },
      legend: { ...baseOption.legend, data: ["Cheapest listing (TSM)", "Market value", "Historical", "Auctionator daily low", "Auctionator daily high", "Forecast"] },
      xAxis: { type: "time", ...axisStyle({ splitLine: { show: false } }) },
      yAxis: { type: "value", scale: true, ...axisStyle({ axisLabel: { color: THEME.muted, formatter: (v: number) => moneyText(v) } }) },
      dataZoom: [{ type: "inside" }, { type: "slider", height: 18, bottom: 6, borderColor: THEME.grid, textStyle: { color: THEME.muted } }],
      grid: { ...baseOption.grid, bottom: 60, left: 80 },
      series: [
        { name: "Cheapest listing (TSM)", type: "line", showSymbol: h.realm.length < 40, step: "end", lineStyle: { width: 1.5 },
          color: THEME.blue, data: h.realm.filter((r) => r.min_buyout).map((r) => [ms(r.t), r.min_buyout]) },
        { name: "Market value", type: "line", showSymbol: h.realm.length < 40, smooth: true, color: THEME.gold,
          data: h.realm.filter((r) => r.market).map((r) => [ms(r.t), r.market]) },
        { name: "Historical", type: "line", showSymbol: h.realm.length < 40, color: THEME.muted, lineStyle: { type: "dashed" },
          data: h.realm.filter((r) => r.historical).map((r) => [ms(r.t), r.historical]) },
        { name: "Auctionator daily low", type: "line", symbolSize: 6, color: THEME.green,
          data: h.auctionator.map((r) => [ms(r.t + 43200), r.low]) },
        { name: "Auctionator daily high", type: "line", symbolSize: 4, color: THEME.violet, lineStyle: { type: "dotted" },
          data: h.auctionator.map((r) => [ms(r.t + 43200), r.high]) },
        { name: "Your posts", type: "scatter", symbol: "diamond", symbolSize: 9, color: THEME.red,
          data: h.postings.map((p) => [ms(p.t), p.price]) },
        ...(stats?.forecast.ok && stats.forecast.points ? [
          { name: "Forecast", type: "line", color: THEME.gold, lineStyle: { type: "dashed", width: 2 }, symbolSize: 5,
            data: stats.forecast.points.map((p) => [ms(p.t), Math.round(p.mean)]) },
          { name: "Forecast low", type: "line", stack: "band", symbol: "none", lineStyle: { opacity: 0 },
            data: stats.forecast.points.map((p) => [ms(p.t), Math.round(p.low)]), tooltip: { show: false } },
          { name: "Forecast range", type: "line", stack: "band", symbol: "none", lineStyle: { opacity: 0 },
            areaStyle: { color: THEME.gold, opacity: 0.12 },
            data: stats.forecast.points.map((p) => [ms(p.t), Math.round(p.high - p.low)]), tooltip: { show: false } },
        ] : []),
      ],
    };
  }, [data, stats]);

  const volumeOption = useMemo(() => {
    if (!data) return null;
    const h = data.history;
    return {
      ...baseOption,
      legend: { ...baseOption.legend, data: ["Sold per day (region)", "Units on AH (your scans)"] },
      grid: { ...baseOption.grid, left: 70, right: 70 },
      xAxis: { type: "time", ...axisStyle({ splitLine: { show: false } }) },
      yAxis: [
        { type: "value", name: "sold/day", ...axisStyle() },
        { type: "value", name: "on AH", ...axisStyle({ splitLine: { show: false } }) },
      ],
      series: [
        { name: "Sold per day (region)", type: "line", step: "end", areaStyle: { opacity: 0.15 }, color: THEME.teal,
          showSymbol: h.region.length < 40, data: h.region.filter((r) => r.sold_per_day !== null).map((r) => [r.t * 1000, r.sold_per_day]) },
        { name: "Units on AH (your scans)", type: "bar", yAxisIndex: 1, color: THEME.violet, barMaxWidth: 18,
          data: h.auctionator.filter((r) => r.available !== null).map((r) => [(r.t + 43200) * 1000, r.available]) },
      ],
    };
  }, [data]);

  if (error) return <div className="error-banner">{error}</div>;
  if (!data) return <div className="loading">Loading...</div>;
  const it = data.item;

  return (
    <section>
      <div className="page-head">
        <button className="link" onClick={() => navigate(-1)}>Back</button>
        <h1>{it.name}</h1>
        <div className="row gap">
          <span className="muted">{it.groups.map((g) => groupTitle(groups, g)).join(", ") || "Not in a profession group"}</span>
          <span className="muted">Item {it.item_id}</span>
          <LabelBadge label={it.label} />
          <Flags flags={it.flags} all />
        </div>
      </div>

      <div className="tiles">
        <Tile title="Price now" hint={COLUMNS.price_now.hint}>
          <Money value={it.price_now} />
          <div className="tile-sub">{it.price_src ? PRICE_SOURCES[it.price_src] : "-"}{it.price_age_h !== null && `, ${ago(Date.now() / 1000 - it.price_age_h * 3600)}`}</div>
        </Tile>
        <Tile title="Usual price" hint={COLUMNS.sell_ref.hint}><Money value={it.sell_ref} /></Tile>
        <Tile title="You keep per sale" hint={COLUMNS.net_sell.hint}>
          <Money value={it.net_sell} />
          <div className="tile-sub">selling at <Money value={it.sell_price} /></div>
        </Tile>
        <Tile title="Reference price" hint={COLUMNS.disc_ref.hint}>
          <Money value={it.reference} />
          <div className={`tile-sub ${(it.disc_ref ?? 0) < 0 ? "pos" : "neg"}`}>now {pct(it.disc_ref, 0, true)}</div>
        </Tile>
        <Tile title="60-day average" hint={COLUMNS.historical.hint}>
          <Money value={it.historical} />
          <div className="tile-sub">now {pct(it.disc_hist, 0, true)}</div>
        </Tile>
        <Tile title="Your sales/day" hint={COLUMNS.my_sales_per_day.hint}>
          {num(it.my_sales_per_day)}
          <div className="tile-sub">region {num(it.sold_per_day_region)}/day, sale rate {pct(it.sale_rate)}</div>
        </Tile>
        <Tile title="Income/day" hint={COLUMNS.income_day.hint}><Money value={it.income_day} /></Tile>
        <Tile title="Flip profit" hint={COLUMNS.flip_profit.hint}>
          <Money value={it.flip_profit} signed />
          <div className="tile-sub">{pct(it.flip_margin, 0, true)} margin, <Money value={it.flip_profit_day} />/day</div>
        </Tile>
        <Tile title="Volatility" hint={COLUMNS.volatility.hint}>
          {pct(it.volatility)}
          <div className="tile-sub">{it.n_points ?? 0} price points, trend {pct(it.trend, 1, true)}/day</div>
        </Tile>
        <Tile title={`Range (${it.n_days ?? 0} days)`} hint="Lowest and highest prices seen in the analysis window.">
          <span className="small"><Money value={it.period_min} /> - <Money value={it.period_max} /></span>
          <div className="tile-sub">today is above {pct(it.pctile)} of them</div>
        </Tile>
        <Tile title="Fees per listing" hint={COLUMNS.deposit.hint}>
          <Money value={it.deposit} />
          <div className="tile-sub">{num(it.listings_per_sale)} listings per sale</div>
        </Tile>
      </div>

      <div className="grid-2">
        <div className="card">
          <h3>What this means</h3>
          <ul className="explain">
            {data.explanation.map((s, i) => <li key={i}>{s}</li>)}
          </ul>
        </div>
        <div className="card">
          <h3>Recipes using this item</h3>
          {data.crafts.length === 0 ? <p className="muted">No known recipe makes or uses this item.</p> : (
            <table className="mini">
              <thead><tr><th className="left">Recipe</th><th>Role</th><th>Profit</th><th>Verdict</th></tr></thead>
              <tbody>
                {data.crafts.map((c) => (
                  <tr key={c.recipe_key}>
                    <td className="left">{c.name}</td>
                    <td>{c.product_id === it.item_id ? "makes it" : "uses it"}</td>
                    <td><Money value={c.profit} signed /></td>
                    <td><VerdictBadge verdict={c.verdict} /></td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
          <p className="muted small"><Link to="/crafts">Open all crafts</Link></p>
        </div>
      </div>

      <StatsCard stats={stats} />

      <div className="card">
        <h3>Price history</h3>
        {priceOption && <Chart option={priceOption as never} height={360} />}
      </div>
      <div className="card">
        <h3>Volume</h3>
        {volumeOption && <Chart option={volumeOption as never} height={260} />}
      </div>
    </section>
  );
}
