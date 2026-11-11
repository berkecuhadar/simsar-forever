import { useEffect } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useApp } from "../context";
import { ago, dateTime, pct } from "../format";
import { useData } from "../hooks";

function permissionLabel() {
  if (!("Notification" in window)) return "not supported by this browser";
  return Notification.permission;
}

export default function StatusPage() {
  const { status, refreshStatus } = useApp();
  const { data: alerts, reload } = useData(api.alerts, [], status?.alerts_unseen ?? 0);

  useEffect(() => {
    if (status && status.alerts_unseen > 0) {
      const t = setTimeout(() => api.markSeen().then(() => { refreshStatus(); reload(); }), 3000);
      return () => clearTimeout(t);
    }
  }, [status?.alerts_unseen]); // eslint-disable-line react-hooks/exhaustive-deps

  if (!status) return <div className="loading">Loading...</div>;
  const s = status;

  return (
    <section>
      <div className="page-head">
        <h1>Data status</h1>
        <p className="lead">Where the numbers come from, how old they are, and what Simsar Forever assumes.</p>
      </div>

      <div className="warnings">
        {s.warnings.length === 0 && <div className="warning ok">Everything looks fine.</div>}
        {s.warnings.map((w, i) => <div key={i} className={`warning ${w.level}`}>{w.message}</div>)}
      </div>

      <div className="card">
        <h3>Sources</h3>
        <table className="mini status-table">
          <thead><tr><th className="left">Source</th><th className="left">State</th><th className="left">Details</th></tr></thead>
          <tbody>
            {s.sources.map((src) => (
              <tr key={src.key}>
                <td className="left"><b>{src.label}</b></td>
                <td className="left"><span className={`dot ${src.ok ? "ok" : src.error ? "err" : "warn"}`} />{src.ok ? "OK" : src.error ? "Error" : "Not available"}</td>
                <td className="left small">
                  {src.key.startsWith("tsm") && <>
                    Scan time {dateTime(src.updated_at)} ({ago(src.updated_at)}), last checked {ago(src.checked_at)}
                    {src.url && <div className="muted">{src.url}</div>}
                  </>}
                  {src.key === "auctionator" && <>
                    {src.items ? `${src.items} items, ` : ""}imported {ago(src.imported_at)}, last full scan {ago(src.last_full_scan)}
                    {src.addon_version && `, Auctionator version ${src.addon_version}`}
                    {src.path && <div className="muted">{src.path}</div>}
                  </>}
                  {src.key === "addon" && <>
                    {src.present ? `${src.recipes ?? 0} recipes, ${src.invoices ?? 0} sale invoices` : "SimsarExport.lua not found yet"}
                    {src.path && <div className="muted">{src.path}</div>}
                  </>}
                  {src.error && <div className="neg">{src.error}</div>}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <div className="grid-2">
        <div className="card">
          <h3>Fees</h3>
          <dl className="kv">
            <dt>Auction house cut</dt><dd>{pct(s.fees.ah_cut, 1)} <span className="muted">({s.fees.cut_source})</span></dd>
            <dt>Deposit</dt><dd>{pct(s.fees.deposit_rate)} of vendor price per {s.fees.auction_hours}h listing <span className="muted">({s.fees.deposit_source})</span></dd>
            <dt>Relist cap</dt><dd>at most {s.fees.max_relists} listings per sale are assumed</dd>
          </dl>
        </div>
        <div className="card">
          <h3>Assumptions <span className="muted small">(edit config.yaml)</span></h3>
          <dl className="kv">
            <dt>TSM data</dt><dd>{s.assumptions.tsm}</dd>
            <dt>Realm share of region sales</dt><dd>{pct(s.assumptions.realm_share)} <span className="muted">(guess, unverified)</span></dd>
            <dt>Your share of realm sales</dt><dd>{pct(s.assumptions.market_share)}</dd>
            <dt>Sell price reference</dt><dd>{s.assumptions.sell_price === "avg_sale" ? "lower of average sale price and market value" : "market value"}</dd>
            <dt>"Cheap" measured against</dt><dd>{s.assumptions.reference_price === "historical" ? "TSM 60-day average" : "TSM market value (two weeks)"}</dd>
            <dt>Analysis window</dt><dd>{s.assumptions.history_days} days</dd>
            <dt>"Profitable" margin</dt><dd>{pct(s.assumptions.good_margin)}</dd>
            <dt>"Fast" seller</dt><dd>{s.assumptions.fast_sales_per_day}+ of your sales per day</dd>
          </dl>
        </div>
      </div>

      <div className="card" id="alerts">
        <h3>Alerts</h3>
        <p className="muted small">
          Simsar Forever checks for cheap items and profitable crafts after every data update. Desktop notifications:{" "}
          <b>{permissionLabel()}</b>
          {"Notification" in window && Notification.permission === "default" && (
            <> <button onClick={() => Notification.requestPermission().then(() => refreshStatus())}>Enable</button></>
          )}
        </p>
        {!alerts?.length ? <p className="muted">No alerts yet.</p> : (
          <ul className="alerts">
            {alerts.map((a) => (
              <li key={a.id} className={a.seen ? "" : "unseen"}>
                <span className="muted small">{dateTime(a.created_at)}</span>{" "}
                {a.item_id ? <Link to={`/item/${a.item_id}`}><b>{a.title}</b></Link> : <b>{a.title}</b>} {a.message}
              </li>
            ))}
          </ul>
        )}
      </div>
      <p className="muted small">Simsar Forever {s.version}. Analysis built {ago(s.built_at)} in {s.build_seconds}s over {s.items} items.</p>
    </section>
  );
}
