import { Link } from "react-router-dom";
import { type Backtest, type LiveAccuracy, api } from "../api";
import { Skeleton } from "../components/Feedback";
import { Hint } from "../components/Hint";
import { useApp } from "../context";
import { num, pct } from "../format";
import { useData } from "../hooks";

// Errors are measured on log prices; shown as the equivalent percentage.
const asPct = (logErr: number | undefined | null) =>
  logErr === undefined || logErr === null ? "-" : pct(Math.expm1(logErr), 1);

function Verdict({ b }: { b: Backtest }) {
  if (!b.ok) return <span className="muted">Not enough data yet: needs {b.needs}.</span>;
  if (b.beats_naive) return <span className="pos">Beats "no change" (p = {num(b.p_value, 3)}).</span>;
  if ((b.skill ?? 0) > 0) return <span className="advice-gradual">Slightly better than "no change", but not yet beyond chance{b.p_value !== null && b.p_value !== undefined ? ` (p = ${num(b.p_value, 2)})` : ""}.</span>;
  return <span className="neg">Not better than "no change".</span>;
}

function BacktestCard({ b, isAdvice }: { b: Backtest; isAdvice: boolean }) {
  return (
    <div className="card">
      <h3>{b.horizon} day{b.horizon === 1 ? "" : "s"} ahead {isAdvice && <span className="muted small">(used for the sell advice)</span>}</h3>
      <p><Verdict b={b} /></p>
      {b.ok && (
        <>
          <dl className="kv">
            <dt><Hint text="Average size of the forecast error, as a percentage of the price.">Typical error</Hint></dt>
            <dd>{asPct(b.mae_model)} <span className="muted">against {asPct(b.mae_naive)} for "no change"</span></dd>
            <dt><Hint text="How much smaller the errors are than those of 'no change'. 0% is no better; negative is worse.">Skill</Hint></dt>
            <dd className={(b.skill ?? 0) > 0 ? "pos" : "neg"}>{pct(b.skill, 1, true)}</dd>
            <dt><Hint text="Share of real outcomes that landed inside the forecast's 80% range. Close to 80% means the ranges can be trusted.">80% range held</Hint></dt>
            <dd>{pct(b.coverage)} <span className="muted">(target 80%)</span></dd>
            <dt><Hint text="When the forecast expected a move of more than 1%, how often the price really moved that way.">Direction right</Hint></dt>
            <dd>{b.direction === null || b.direction === undefined ? "-" : `${pct(b.direction)} of ${b.direction_n}`}</dd>
            <dt>Tested on</dt>
            <dd>{b.n.toLocaleString("en-US")} forecasts over {b.days} day{b.days === 1 ? "" : "s"}</dd>
          </dl>
          {b.hold && b.sell && (
            <>
              <div className="list-title">If you had followed the advice</div>
              <dl className="kv">
                <dt><Hint text="Forecasts that would have said 'hold'. Right = the price really was higher after the horizon.">Hold calls</Hint></dt>
                <dd>{b.hold.n ? <>{b.hold.n}, right {pct(b.hold.hit)}, average change {pct(b.hold.avg_change, 1, true)}</> : "none"}</dd>
                <dt><Hint text="All other forecasts. If prices often rose a lot after them, 'sell now' was leaving money on the table.">Other calls</Hint></dt>
                <dd>{b.sell.n}, average change {pct(b.sell.avg_change, 1, true)}, rose over 5% in {pct(b.sell.rose_much)}</dd>
              </dl>
            </>
          )}
          {b.calibration && b.calibration.length > 0 && (
            <>
              <div className="list-title">
                <Hint text="When the model said 'X% chance of a rise', how often the price really rose. The chance is corrected with the outcomes of earlier forecasts (isotonic calibration), using only what was known on the day. Good calibration means the two columns match.">Chance of a rise: said vs happened</Hint>
              </div>
              <table className="mini">
                <thead><tr><th className="left">Said</th><th>Happened</th><th>Forecasts</th></tr></thead>
                <tbody>
                  {b.calibration.map((c) => (
                    <tr key={c.from}><td className="left">{pct(c.predicted)}</td><td>{pct(c.observed)}</td><td className="muted">{c.n}</td></tr>
                  ))}
                </tbody>
              </table>
            </>
          )}
        </>
      )}
    </div>
  );
}

function LiveRow({ l }: { l: LiveAccuracy }) {
  return (
    <tr>
      <td className="left">{l.horizon} day{l.horizon === 1 ? "" : "s"}</td>
      <td>{l.n}</td>
      <td className="muted">{l.pending}</td>
      <td>{l.ok ? <>{asPct(l.mae_model)} <span className="muted">vs {asPct(l.mae_naive)}</span></> : "-"}</td>
      <td className={l.ok ? ((l.skill ?? 0) > 0 ? "pos" : "neg") : ""}>{l.ok ? pct(l.skill, 1, true) : "-"}</td>
      <td>{l.ok ? pct(l.coverage) : "-"}</td>
      <td>{l.ok && l.hold?.n ? `${l.hold.n}, right ${pct(l.hold.hit)}` : "-"}</td>
    </tr>
  );
}

export default function Accuracy() {
  const { version } = useApp();
  const { data, error } = useData(api.accuracy, [], version);
  if (error) return <div className="error-banner">{error}</div>;
  if (!data) return <Skeleton />;
  const horizons = Object.keys(data.backtest).sort((a, b) => Number(a) - Number(b));
  const advice = data.advice;

  return (
    <section>
      <div className="page-head">
        <h1>Forecast accuracy</h1>
        <p className="lead">
          The sell plan only says "hold" when its price forecasts have been right more often than simply assuming the
          price stays where it is. This page shows how they have done. For every past day the model is rebuilt from
          what was known that day only, and its forecasts are checked against what happened next.
        </p>
      </div>

      <div className="warning" style={{ marginBottom: 18 }}>
        <span>
          {data.hold_allowed
            ? <><b>Hold advice is on</b>: the {advice.horizon_days}-day forecasts beat "no change" with statistical evidence. </>
            : <><b>Hold advice is off</b>: the {advice.horizon_days}-day forecasts have not yet shown they beat "no change". </>}
          Hold needs an expected rise of at least {pct(advice.hold_min_gain)} with at least {pct(advice.hold_min_probability)}
          {" "}chance. Based on {data.days} days of prices for {data.items.toLocaleString("en-US")} items. <Link to="/sell">Sell plan</Link>
        </span>
      </div>

      <h2 className="section-title">Backtest</h2>
      <div className="stats-grid">
        {horizons.map((h) => <BacktestCard key={h} b={data.backtest[h]} isAdvice={Number(h) === advice.horizon_days} />)}
      </div>

      <h2 className="section-title">
        Live record <Hint text="Each day Simsar Forever stores its forecasts for the items you track or hold, and checks them once the day they were about arrives. Unlike the backtest, nothing here could have been tuned after the fact." />
      </h2>
      <div className="table-wrap">
        <table className="data">
          <thead>
            <tr>
              <th className="left">Horizon</th><th>Checked</th><th>Waiting</th><th>Typical error</th><th>Skill</th>
              <th>80% range held</th><th>Hold calls</th>
            </tr>
          </thead>
          <tbody>
            {Object.keys(data.live).sort((a, b) => Number(a) - Number(b)).map((h) => <LiveRow key={h} l={data.live[h]} />)}
          </tbody>
        </table>
      </div>
      <p className="muted small">Numbers appear once at least 30 forecasts of a horizon have been checked.</p>

      <h2 className="section-title">The model</h2>
      <div className="card">
        <p>
          One model for all items. Each day, an item's price is compared with its median over the last two weeks. The
          model learns, from every item at once, how much of that gap usually closes within 1, 3 and 7 days, and how
          much all prices drift together. Uncertain coefficients are pulled towards zero, so the forecast falls back to
          "no change" when the data says nothing clear.
        </p>
        <table className="mini">
          <thead>
            <tr><th className="left">Horizon</th><th>Gap that closes</th><th>Market drift</th><th>t statistic</th><th>Pairs used</th></tr>
          </thead>
          <tbody>
            {Object.values(data.models).map((m) => (
              <tr key={m.H}>
                <td className="left">{m.H} day{m.H === 1 ? "" : "s"}</td>
                <td>{pct(-m.b)}</td>
                <td>{pct(Math.expm1(m.a), 1, true)}</td>
                <td>{num(m.b_t, 1)}</td>
                <td>{m.n.toLocaleString("en-US")}</td>
              </tr>
            ))}
            {Object.keys(data.models).length === 0 && (
              <tr><td colSpan={5} className="left muted">Not enough price history to fit the model yet.</td></tr>
            )}
          </tbody>
        </table>
        <p className="muted small">See docs/metrics.md for the formulas.</p>
      </div>
    </section>
  );
}
