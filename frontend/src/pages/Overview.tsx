import { Link } from "react-router-dom";
import { type GroupOverview, api } from "../api";
import { Flags } from "../components/Badges";
import { Hint } from "../components/Hint";
import { useApp } from "../context";
import { Money, num } from "../format";
import { useData } from "../hooks";

function Warnings() {
  const { status } = useApp();
  const shown = (status?.warnings ?? []).filter((w) => w.level !== "demo");
  if (!shown.length) return null;
  return (
    <div className="warnings">
      {shown.slice(0, 4).map((w, i) => <div key={i} className={`warning ${w.level}`}>{w.message}</div>)}
      {shown.length > 4 && <Link to="/status">{shown.length - 4} more on the data status page</Link>}
    </div>
  );
}

function GroupCard({ g }: { g: GroupOverview }) {
  const isGather = g.role === "gather";
  const list = isGather ? g.top_sellers : g.top_flips;
  return (
    <div className="card group-card" style={{ borderTopColor: g.color }}>
      <div className="group-head">
        <h3>{g.title}</h3>
        <span className="muted small">{g.items} items, {g.with_volume} with sales data</span>
      </div>
      <div className="group-stats">
        <div>
          <div className="stat-label">Market size/day <Hint text="Money spent per day on this group's items on your realm (estimated)." /></div>
          <div className="stat"><Money value={g.turnover_day} /></div>
        </div>
        {g.role === "craft" && (
          <div>
            <div className="stat-label">Profitable crafts <Hint text="Recipes that make money even when you buy every material." /></div>
            <div className="stat">{g.profitable_crafts} / {g.recipes}</div>
          </div>
        )}
      </div>
      {g.top_crafts.length > 0 && (
        <>
          <div className="list-title">Best crafts</div>
          <ul className="toplist">
            {g.top_crafts.map((c) => (
              <li key={c.recipe_key}>
                <Link to="/crafts">{c.name}</Link>
                <span><Money value={c.profit_day ?? c.profit} />{c.profit_day !== null ? "/day" : " each"}</span>
              </li>
            ))}
          </ul>
        </>
      )}
      <div className="list-title">{isGather ? "Best to sell (income/day)" : "Best flips (score)"}</div>
      {list.length === 0 ? <p className="muted small">Nothing stands out yet.</p> : (
        <ul className="toplist">
          {list.map((i) => (
            <li key={i.item_id}>
              <Link to={`/item/${i.item_id}`}>{i.name}</Link>
              <span><Money value={i.value} />/day <Flags flags={i.flags} /></span>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function Overview() {
  const { status, version } = useApp();
  const { data } = useData(api.overview, [], version);
  return (
    <section>
      <div className="page-head">
        <h1>Overview</h1>
        <p className="lead">
          Your professions at a glance. Gathering groups show what earns the most when you sell your own stock;
          crafting groups show the best recipes and resale chances. Every number has a <Hint text="Like this one." /> with
          an explanation, and the <Link to="/glossary">glossary</Link> explains the terms.
        </p>
      </div>
      <Warnings />
      {status && (
        <div className="summary-strip">
          <span><b>{num(status.tracked_items, 0)}</b> tracked items</span>
          <span><b>{status.recipes}</b> recipes</span>
          <span>AH cut <b>{(status.fees.ah_cut * 100).toFixed(1)}%</b> <span className="muted">({status.fees.cut_source})</span></span>
          <span>Your realm share <b>{(status.assumptions.realm_share * 100).toFixed(0)}%</b>, your market share <b>{(status.assumptions.market_share * 100).toFixed(0)}%</b>
            <Hint text="Assumptions from config.yaml that turn region-wide sales into what you can sell. Change them there." /></span>
        </div>
      )}
      {!data ? <div className="loading">Loading...</div> : (
        <div className="group-grid">
          {data.groups.map((g) => <GroupCard key={g.key} g={g} />)}
        </div>
      )}
    </section>
  );
}
