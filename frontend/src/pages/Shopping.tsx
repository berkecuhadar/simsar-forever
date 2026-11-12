import { useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { type Craft, api } from "../api";
import { Skeleton, toast } from "../components/Feedback";
import { Hint } from "../components/Hint";
import { ItemIcon, ItemName } from "../components/Icons";
import { useApp } from "../context";
import { Money, num } from "../format";
import { useData, useStored } from "../hooks";
import { VERDICTS } from "../strings";

interface Entry { recipe_key: string; crafts: number }

const STORE = "simsar-forever:shopping.list";

/** Add one craft of a recipe to the shopping list from another page. */
export function addToShoppingList(recipe_key: string, name: string) {
  try {
    const list: Entry[] = JSON.parse(localStorage.getItem(STORE) ?? "[]");
    const hit = list.find((e) => e.recipe_key === recipe_key);
    if (hit) hit.crafts += 1; else list.push({ recipe_key, crafts: 1 });
    localStorage.setItem(STORE, JSON.stringify(list));
    toast(`${name} added to the shopping list.`, "success");
  } catch {
    toast("The shopping list could not be saved in this browser.", "error");
  }
}

interface Need {
  key: string;
  item_id: number | null;
  name: string;
  need: number;
  have: number;
  buy: number;
  unit_price: number | null;
  price_src: "auction" | "vendor" | null;
  unit_net_sell: number | null;
  craft?: { name: string; unit_cost: number };
}

export default function Shopping() {
  const { version } = useApp();
  const crafts = useData(api.crafts, [], version);
  const inv = useData(api.inventory, [], version);
  const [list, setList] = useStored<Entry[]>("shopping.list", []);
  const [useStock, setUseStock] = useStored("shopping.useStock", true);
  const [query, setQuery] = useState("");
  const [params, setParams] = useSearchParams();

  // ?add=<recipe key> puts one craft of that recipe on the list (links from other pages).
  useEffect(() => {
    const key = params.get("add");
    if (!key) return;
    setList((old) => old.some((e) => e.recipe_key === key) ? old : [...old, { recipe_key: key, crafts: 1 }]);
    setParams({}, { replace: true });
  }, [params, setParams, setList]);

  const byKey = useMemo(() => Object.fromEntries((crafts.data ?? []).map((c) => [c.recipe_key, c])), [crafts.data]);
  const held = useMemo(() => {
    const out: Record<number, number> = {};
    for (const i of inv.data?.items ?? []) out[i.item_id] = (out[i.item_id] ?? 0) + i.count - i.bound;
    return out;
  }, [inv.data]);
  // The cheapest way to make one unit of an item that some recipe produces.
  const craftable = useMemo(() => {
    const out: Record<number, { name: string; unit_cost: number }> = {};
    for (const c of crafts.data ?? []) {
      if (!c.product_id || c.cost_buy === null || !c.yield) continue;
      const unit = c.cost_buy / c.yield;
      if (!out[c.product_id] || unit < out[c.product_id].unit_cost) out[c.product_id] = { name: c.name, unit_cost: unit };
    }
    return out;
  }, [crafts.data]);

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return [];
    return (crafts.data ?? []).filter((c) => c.name.toLowerCase().includes(q) || c.product_name.toLowerCase().includes(q)
      || c.profession.toLowerCase().includes(q)).slice(0, 12);
  }, [crafts.data, query]);

  const entries = list.filter((e) => byKey[e.recipe_key]);
  const needs = useMemo(() => {
    const out = new Map<string, Need>();
    for (const e of entries) {
      for (const r of byKey[e.recipe_key].reagents) {
        const key = r.item_id ? String(r.item_id) : r.name;
        const n = out.get(key) ?? { key, item_id: r.item_id, name: r.name, need: 0, have: 0, buy: 0, unit_price: r.unit_price,
          price_src: r.price_src, unit_net_sell: r.unit_net_sell };
        n.need += r.count * e.crafts;
        out.set(key, n);
      }
    }
    for (const n of out.values()) {
      n.have = useStock && n.item_id ? Math.min(held[n.item_id] ?? 0, n.need) : 0;
      n.buy = n.need - n.have;
      const c = n.item_id ? craftable[n.item_id] : undefined;
      if (c && n.unit_price && c.unit_cost < n.unit_price * 0.95) n.craft = c;
    }
    return [...out.values()].sort((a, b) => (b.buy * (b.unit_price ?? 0)) - (a.buy * (a.unit_price ?? 0)));
  }, [entries, byKey, held, craftable, useStock]); // eslint-disable-line react-hooks/exhaustive-deps

  const totals = useMemo(() => {
    let buyCost = 0, ownValue = 0, missing = 0, revenue = 0, units = 0;
    for (const n of needs) {
      if (n.unit_price) buyCost += n.buy * n.unit_price; else if (n.buy) missing += 1;
      ownValue += n.have * (n.unit_net_sell ?? (n.unit_price ?? 0) * 0.95);
    }
    let days = 0;
    for (const e of entries) {
      const c = byKey[e.recipe_key];
      revenue += (c.revenue ?? 0) * e.crafts;
      units += c.yield * e.crafts;
      if (c.product_sales_per_day) days = Math.max(days, (c.yield * e.crafts) / c.product_sales_per_day);
    }
    return { buyCost, ownValue, missing, revenue, units, days, profit: revenue - buyCost - ownValue };
  }, [needs, entries, byKey]);

  const add = (c: Craft) => {
    setList((old) => old.some((e) => e.recipe_key === c.recipe_key)
      ? old.map((e) => e.recipe_key === c.recipe_key ? { ...e, crafts: e.crafts + 1 } : e)
      : [...old, { recipe_key: c.recipe_key, crafts: 1 }]);
    setQuery("");
  };
  const setCrafts = (key: string, crafts: number) =>
    setList((old) => old.map((e) => e.recipe_key === key ? { ...e, crafts: Math.max(1, Math.round(crafts) || 1) } : e));
  const remove = (key: string) => setList((old) => old.filter((e) => e.recipe_key !== key));

  const copy = () => {
    const text = needs.filter((n) => n.buy > 0).map((n) => `${num(n.buy, 0)} x ${n.name}`).join("\n");
    navigator.clipboard.writeText(text).then(() => toast("Shopping list copied.", "success"),
      () => toast("Could not copy to the clipboard.", "error"));
  };

  if (crafts.error) return <div className="error-banner">{crafts.error}</div>;
  if (!crafts.data) return <Skeleton />;

  return (
    <section>
      <div className="page-head">
        <h1>Shopping list</h1>
        <p className="lead">
          Pick what you want to craft. Simsar adds up the materials, takes off what your characters already hold in
          bags and banks, and tells you what is left to buy, where it is cheapest and what the batch should earn.
        </p>
      </div>

      <div className="card">
        <h3>What to craft</h3>
        <div className="filters" style={{ marginTop: 0 }}>
          <input style={{ minWidth: 320 }} placeholder="Search recipes, products or professions" value={query}
            onChange={(e) => setQuery(e.target.value)} />
          <label className="check">
            <input type="checkbox" checked={useStock} onChange={(e) => setUseStock(e.target.checked)} />
            Use what my characters hold
          </label>
          <span className="spacer" />
          {entries.length > 0 && <button onClick={() => setList([])}>Clear</button>}
        </div>
        {matches.length > 0 && (
          <ul className="picker">
            {matches.map((c) => (
              <li key={c.recipe_key}>
                <button className="link" onClick={() => add(c)}>
                  <span className="item-name">
                    <ItemIcon id={c.product_icon} quality={c.product_quality} />
                    <ItemName name={c.name} quality={c.product_quality} />
                  </span>
                </button>
                <span className="muted small">{c.profession}</span>
                <span className={`badge verdict-${c.verdict} small`}>{VERDICTS[c.verdict]}</span>
                <span className="small">profit <Money value={c.profit} signed /></span>
              </li>
            ))}
          </ul>
        )}
        {entries.length === 0 ? (
          <p className="muted">Nothing on the list yet. Search for a recipe above, or add one from the <Link to="/crafts">Crafts</Link> page.</p>
        ) : (
          <table className="mini" style={{ width: "100%" }}>
            <thead>
              <tr><th className="left">Recipe</th><th>Crafts</th><th>Makes</th><th>Profit each</th><th>Sells per day</th><th /></tr>
            </thead>
            <tbody>
              {entries.map((e) => {
                const c = byKey[e.recipe_key];
                return (
                  <tr key={e.recipe_key}>
                    <td className="left">
                      <span className="item-name">
                        <ItemIcon id={c.product_icon} quality={c.product_quality} />
                        <ItemName name={c.name} quality={c.product_quality} />
                        <span className="muted small">{c.profession}</span>
                      </span>
                    </td>
                    <td><input type="number" min={1} value={e.crafts} style={{ width: 80 }}
                      onChange={(ev) => setCrafts(e.recipe_key, Number(ev.target.value))} /></td>
                    <td>{num(c.yield * e.crafts, 0)}</td>
                    <td><Money value={c.profit} signed /></td>
                    <td>{num(c.product_sales_per_day)}</td>
                    <td><button className="link" onClick={() => remove(e.recipe_key)}>Remove</button></td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </div>

      {entries.length > 0 && (
        <>
          <div className="tiles">
            <div className="tile">
              <div className="tile-title">To buy</div>
              <div className="tile-value"><Money value={totals.buyCost} /></div>
              {totals.missing > 0 && <div className="tile-sub neg">{totals.missing} material{totals.missing === 1 ? "" : "s"} without a price</div>}
            </div>
            <div className="tile">
              <div className="tile-title">Your own materials <Hint text="What the materials you already hold would bring if you sold them instead. Crafting with them costs you that." /></div>
              <div className="tile-value"><Money value={totals.ownValue} /></div>
            </div>
            <div className="tile">
              <div className="tile-title">Selling the results <Hint text="What selling everything you craft leaves you after the auction house cut, at today's prices." /></div>
              <div className="tile-value"><Money value={totals.revenue} /></div>
              <div className="tile-sub">
                {num(totals.units, 0)} item{totals.units === 1 ? "" : "s"}
                {totals.days > 0 && (totals.days < 1 ? ", sells within a day" : `, about ${num(totals.days, 0)} days to sell`)}
              </div>
            </div>
            <div className="tile">
              <div className="tile-title">Expected profit <Hint text="Selling the results minus buying the missing materials minus the value of your own materials." /></div>
              <div className="tile-value"><Money value={totals.profit} signed /></div>
            </div>
          </div>

          <div className="filters">
            <h2 style={{ margin: 0 }}>Materials</h2>
            <span className="spacer" />
            <button onClick={copy}>Copy what to buy</button>
          </div>
          <div className="table-wrap">
            <table className="data">
              <thead>
                <tr>
                  <th className="left">Material</th><th>Need</th><th>You have</th><th>Buy</th><th className="left">Where</th>
                  <th>Each</th><th>Cost</th><th className="left">Note</th>
                </tr>
              </thead>
              <tbody>
                {needs.map((n) => (
                  <tr key={n.key} className={n.buy === 0 ? "done" : ""}>
                    <td className="left">
                      {n.item_id ? <Link to={`/item/${n.item_id}`}>{n.name}</Link> : n.name}
                    </td>
                    <td>{num(n.need, 0)}</td>
                    <td>{n.have ? num(n.have, 0) : <span className="muted">-</span>}</td>
                    <td><b>{n.buy ? num(n.buy, 0) : <span className="pos">done</span>}</b></td>
                    <td className="left">{n.buy ? (n.price_src === "vendor" ? "Vendor" : n.price_src === "auction" ? "Auction house" : "-") : ""}</td>
                    <td><Money value={n.unit_price} /></td>
                    <td><Money value={n.buy && n.unit_price ? n.buy * n.unit_price : null} /></td>
                    <td className="left small">
                      {n.craft && n.buy > 0 && (
                        <span className="advice-gradual">Cheaper to craft ({n.craft.name}): <Money value={n.craft.unit_cost} /> each</span>
                      )}
                      {!n.unit_price && n.buy > 0 && <span className="neg">No price known</span>}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
