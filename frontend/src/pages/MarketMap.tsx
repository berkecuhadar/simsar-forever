import { useMemo } from "react";
import { Skeleton } from "../components/Feedback";
import { useNavigate } from "react-router-dom";
import { type Item, api } from "../api";
import { Chart, THEME, axisStyle, baseOption } from "../components/Chart";
import { Hint } from "../components/Hint";
import { useApp } from "../context";
import { moneyText, num, pct } from "../format";
import { useData, useStored } from "../hooks";

const Y_METRICS: Record<string, { label: string; get: (i: Item) => number | null; hint: string }> = {
  flip_margin: { label: "Flip margin", get: (i) => i.flip_margin,
    hint: "Profit from buying at the cheapest listing and reselling at the usual price, as a share of the buy price." },
  disc_ref: { label: "Price vs usual", get: (i) => i.disc_ref,
    hint: "How far today's cheapest listing is from the item's usual price. Below zero is cheaper than usual." },
  volatility: { label: "Volatility", get: (i) => i.volatility,
    hint: "How much the price swings day to day. Higher is riskier." },
  trend: { label: "Trend per day", get: (i) => i.trend, hint: "Typical price change per day." },
};

export default function MarketMap() {
  const { groups, version } = useApp();
  const { data } = useData(() => api.items("tracked"), [], version);
  const [s, setS] = useStored("map", { y: "flip_margin", clip: true });
  const navigate = useNavigate();
  const metric = Y_METRICS[s.y] ?? Y_METRICS.flip_margin;

  const option = useMemo(() => {
    const items = (data ?? []).filter((i) => i.my_sales_per_day && i.my_sales_per_day > 0 && metric.get(i) !== null);
    const maxTurnover = Math.max(1, ...items.map((i) => i.turnover_day ?? 0));
    const series = groups.map((g) => ({
      name: g.title,
      type: "scatter",
      itemStyle: { color: g.color, opacity: 0.8, borderColor: "#0d1017", borderWidth: 1 },
      emphasis: { focus: "series" },
      data: items.filter((i) => i.group === g.key).map((i) => {
        let y = metric.get(i)!;
        if (s.clip) y = Math.max(-1, Math.min(1, y));
        return {
          value: [i.my_sales_per_day, y],
          symbolSize: 6 + 34 * Math.sqrt((i.turnover_day ?? 0) / maxTurnover),
          item: i,
        };
      }),
    }));
    return {
      ...baseOption,
      legend: { ...baseOption.legend, selected: { Recipes: false } },
      grid: { left: 70, right: 30, top: 40, bottom: 56 },
      tooltip: {
        ...baseOption.tooltip, trigger: "item",
        formatter: (p: { data: { item: Item } }) => {
          const i = p.data.item;
          return `<b>${i.name}</b><br/>Price now: ${moneyText(i.price_now)}<br/>Your sales/day: ${num(i.my_sales_per_day)}` +
            `<br/>${metric.label}: ${pct(metric.get(i), 1, true)}<br/>Market size/day: ${moneyText(i.turnover_day)}`;
        },
      },
      xAxis: { type: "log", name: "Your expected sales per day (log scale)", nameLocation: "middle", nameGap: 32,
        ...axisStyle() },
      yAxis: { type: "value", name: metric.label, ...axisStyle({ axisLabel: { color: THEME.muted, formatter: (v: number) => pct(v) } }) },
      series: [
        ...series,
        { type: "line", markLine: { silent: true, symbol: "none", label: { show: false }, lineStyle: { color: THEME.muted, type: "dashed" },
          data: [{ yAxis: 0 }] }, data: [] },
      ],
    };
  }, [data, groups, metric, s.clip]);

  return (
    <section>
      <div className="page-head">
        <h1>Market map</h1>
        <p className="lead">
          Each bubble is an item. Further right sells faster, higher has a better {metric.label.toLowerCase()}, and a
          bigger bubble means more money changes hands for it each day. The best spots are top right with big bubbles.
          Click a group in the legend to show or hide it (recipes start hidden).
          <Hint text={metric.hint} />
        </p>
      </div>
      <div className="filters">
        <label>
          Vertical axis
          <select value={s.y} onChange={(e) => setS({ ...s, y: e.target.value })}>
            {Object.entries(Y_METRICS).map(([k, m]) => <option key={k} value={k}>{m.label}</option>)}
          </select>
        </label>
        <label className="check">
          <input type="checkbox" checked={s.clip} onChange={(e) => setS({ ...s, clip: e.target.checked })} />
          Clip extreme values to +/-100%
        </label>
      </div>
      <div className="card">
        {!data ? <Skeleton /> : (
          <Chart option={option as never} height={560}
            onClick={(p) => navigate(`/item/${(p.data as { item: Item }).item.item_id}`)} />
        )}
      </div>
    </section>
  );
}
