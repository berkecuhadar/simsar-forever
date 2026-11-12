import type { ItemStats } from "../api";
import { Money, num, pct } from "../format";
import { Hint } from "./Hint";

function Needs({ text }: { text: string }) {
  return <p className="muted small">Not enough data yet: needs {text}. History grows while Simsar Forever runs.</p>;
}

export function StatsCard({ stats }: { stats: ItemStats | null }) {
  if (!stats) return <div className="card"><h3>Advanced statistics</h3><div className="loading">Calculating...</div></div>;
  const { mean_reversion: mr, forecast: fc, elasticity: el, timing: tm } = stats;

  return (
    <div className="card">
      <h3>Advanced statistics <Hint text="Time-series statistics on this item's own history (statsmodels and SciPy). They describe the past; markets can change at any time." /></h3>
      <div className="stats-grid">
        <div>
          <div className="stat-title"><Hint text="An AR(1) model on log prices measures how fast gaps from the usual level close; the half-life is how long half a gap takes. The ADF test checks the pull is real and not chance (p below 0.05 = strong evidence).">Does the price snap back?</Hint></div>
          {!mr.ok ? <Needs text={mr.needs!} /> : mr.verdict === "none" ? (
            <p>No reliable pull back to a fixed level (ADF p = {num(mr.adf_p, 2)}). The price behaves more like a drifting
              walk, so "it will come back" is not a safe bet.</p>
          ) : (
            <p>
              Yes, {mr.verdict === "strong" ? "clearly" : "weakly"}: a gap from <Money value={mr.equilibrium} /> halves in
              about <b>{num(mr.half_life_days, 1)} days</b> (ADF p = {num(mr.adf_p, 3)}). Cheap listings tend to be
              bought or the price recovers within roughly that time.
            </p>
          )}
        </div>

        <div>
          <div className="stat-title"><Hint text="Exponential smoothing with a damped trend (ETS) on daily prices. The range is an 80% interval: in 4 cases out of 5 the price should land inside it, if the market keeps behaving as it has.">Price forecast (3 days)</Hint></div>
          {!fc.ok ? <Needs text={fc.needs!} /> : fc.flat ? <p>The price has not moved, so the forecast is flat.</p> : (
            <>
              <p>
                Expected around <Money value={fc.points![fc.points!.length - 1].mean} />{" "}
                (<span className={(fc.change ?? 0) < 0 ? "neg" : "pos"}>{pct(fc.change, 1, true)}</span>), likely between{" "}
                <Money value={fc.points![fc.points!.length - 1].low} /> and <Money value={fc.points![fc.points!.length - 1].high} />.
              </p>
              <p className="muted small">Shown as a dashed line on the price chart. Based on {fc.days_used} days.</p>
            </>
          )}
        </div>

        <div>
          <div className="stat-title"><Hint text="Elasticity from a log-log regression of daily units sold on the average sale price across the region. -2 means a 1% higher price goes with 2% fewer sales. It is a correlation: supply changes also move both.">Price sensitivity of demand</Hint></div>
          {!el.ok ? <Needs text={el.needs!} /> : !el.clear ? (
            <p>No clear link between price and sales so far (elasticity {num(el.elasticity, 2)}, 90% range {num(el.ci_low, 2)} to {num(el.ci_high, 2)}).</p>
          ) : (
            <p>
              Elasticity <b>{num(el.elasticity, 2)}</b> (90% range {num(el.ci_low, 2)} to {num(el.ci_high, 2)}, R² {num(el.r2, 2)}):{" "}
              {el.elasticity! < -1 ? "buyers react strongly to price; undercutting wins many extra sales."
                : el.elasticity! < 0 ? "buyers react mildly; a higher price costs relatively few sales."
                : "sales rise with the price, a sign that demand shifts drive both."}
            </p>
          )}
        </div>

        <div>
          <div className="stat-title"><Hint text="Each scan's price relative to that day's median, grouped by local time of day (and weekday after two weeks). The Kruskal-Wallis test says whether the differences are bigger than chance.">Best time to buy and sell</Hint></div>
          {!tm.ok ? <Needs text={tm.needs!} /> : !tm.hours ? <Needs text="scans spread across more hours" /> : (
            <>
              <p>
                Cheapest around <b>{tm.hours.cheapest}</b> ({pct(tm.hours.cheapest_gap, 1, true)}), dearest around{" "}
                <b>{tm.hours.dearest}</b> ({pct(tm.hours.dearest_gap, 1, true)}).{" "}
                {tm.hours.significant ? "The pattern is statistically clear." : `Could still be chance (p = ${num(tm.hours.p, 2)}).`}
              </p>
              {tm.weekdays && (
                <p>
                  By weekday: cheapest on <b>{tm.weekdays.cheapest}</b>, dearest on <b>{tm.weekdays.dearest}</b>
                  {tm.weekdays.significant ? "." : ` (not significant, p = ${num(tm.weekdays.p, 2)}).`}
                </p>
              )}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
