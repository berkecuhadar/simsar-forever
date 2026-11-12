import type { ColumnDef } from "@tanstack/react-table";
import { useMemo } from "react";
import { Link, useNavigate } from "react-router-dom";
import { type ProfessionRecipe, api } from "../api";
import { VerdictBadge } from "../components/Badges";
import { DataTable, downloadCsv } from "../components/DataTable";
import { Skeleton } from "../components/Feedback";
import { Hint } from "../components/Hint";
import { ItemIcon, ItemName } from "../components/Icons";
import { useApp } from "../context";
import { Money, ago, num } from "../format";
import { useData, useStored } from "../hooks";
import { CLASS_COLORS } from "./Inventory";

const PROFESSIONS = ["Alchemy", "Blacksmithing", "Cooking", "Enchanting", "Engineering", "First Aid", "Fishing",
  "Herbalism", "Inscription", "Jewelcrafting", "Leatherworking", "Mining", "Skinning", "Tailoring"];

const VIA: Record<string, string> = { trainer: "Trainer", vendor: "Vendor", auction: "Auction house" };

function howToGet(r: ProfessionRecipe) {
  const out: JSX.Element[] = [];
  if (r.trainer_cost !== null) out.push(<span key="t">Trainer <Money value={r.trainer_cost} /></span>);
  if (r.vendor) out.push(
    <span key="v">
      Vendor <Money value={r.vendor.price} />
      <span className="muted">{r.vendor.vendor ? ` (${r.vendor.vendor}${r.vendor.zone ? `, ${r.vendor.zone}` : ""})` : ""}{r.vendor.limited ? ", limited stock" : ""}</span>
    </span>);
  if (r.auction) out.push(<span key="a">Auction house <Link to={`/item/${r.auction.item_id}`}><Money value={r.auction.price} /></Link></span>);
  if (!out.length) return <span className="muted">Not seen for sale yet</span>;
  return <span className="ways">{out}</span>;
}

export default function Professions() {
  const { version } = useApp();
  const { data, error } = useData(api.professions, [], version);
  const [f, setF] = useStored("professions.filters", { char: "", profession: "", learnableOnly: true, canLearnOnly: false });
  const [sorting, setSorting] = useStored("professions.sort", [{ id: "profit_day", desc: true }]);
  const navigate = useNavigate();

  const chars = data?.characters ?? [];
  const char = chars.find((c) => c.char_key === f.char) ?? chars.find((c) => c.professions.length) ?? chars[0];
  const profs = useMemo(() => {
    const own = char?.professions.map((p) => p.profession) ?? [];
    const all = (data?.professions ?? []).filter((p) => PROFESSIONS.includes(p));
    return [...own, ...all.filter((p) => !own.includes(p))];
  }, [char, data]);
  const profession = f.profession && profs.includes(f.profession) ? f.profession : profs[0] ?? "";
  const skill = char?.professions.find((p) => p.profession === profession);

  const rows = useMemo(() => (data?.recipes ?? []).filter((r) => {
    if (r.profession !== profession) return false;
    const key = char?.char_key ?? "";
    const knows = r.known_by.includes(key) || (!r.unknown_by.includes(key) && r.learned_any === 1 && !char?.professions.length);
    if (f.learnableOnly && knows) return false;
    if (f.canLearnOnly && skill && r.skill_req !== null && r.skill_req > skill.rank) return false;
    return true;
  }), [data, profession, char, f.learnableOnly, f.canLearnOnly, skill]);

  const columns = useMemo<ColumnDef<ProfessionRecipe, unknown>[]>(() => [
    { id: "name", header: "Recipe", accessorFn: (r) => r.name, meta: { align: "left", csv: (r: ProfessionRecipe) => r.name },
      cell: ({ row }) => (
        <span className="item-name">
          <ItemIcon id={row.original.product_icon} quality={row.original.product_quality} />
          <ItemName name={row.original.name} quality={row.original.product_quality} />
        </span>
      ) },
    { id: "skill_req", header: "Skill", accessorFn: (r) => r.skill_req ?? -1,
      meta: { hint: "Skill needed to learn it, from the trainer or the recipe's tooltip. Green: this character can learn it now.",
        csv: (r: ProfessionRecipe) => r.skill_req },
      cell: ({ row }) => {
        const req = row.original.skill_req;
        if (req === null) return <span className="muted">?</span>;
        return <span className={skill ? (req <= skill.rank ? "pos" : "neg") : ""}>{req}</span>;
      } },
    { id: "get", header: "How to get it", enableSorting: false, accessorFn: (r) => r.learn_via ?? "",
      meta: { align: "left", csv: (r: ProfessionRecipe) => r.learn_via ? VIA[r.learn_via] : "" },
      cell: ({ row }) => howToGet(row.original) },
    { id: "learn_cost", header: "Cost to learn", accessorFn: (r) => r.learn_cost ?? Infinity,
      meta: { hint: "The cheapest known way to get the recipe.", csv: (r: ProfessionRecipe) => r.learn_cost },
      cell: ({ row }) => <Money value={row.original.learn_cost} /> },
    { id: "verdict", header: "Verdict", accessorFn: (r) => r.verdict, meta: { align: "left", csv: (r: ProfessionRecipe) => r.verdict },
      cell: ({ row }) => <VerdictBadge verdict={row.original.verdict} /> },
    { id: "profit", header: "Profit each", accessorFn: (r) => r.profit ?? -Infinity,
      meta: { hint: "Crafting and selling one, buying all materials at today's prices.", csv: (r: ProfessionRecipe) => r.profit },
      cell: ({ row }) => <Money value={row.original.profit} signed /> },
    { id: "profit_day", header: "Profit/day", accessorFn: (r) => r.profit_day ?? -Infinity,
      meta: { hint: "Profit each x how many you can sell per day.", csv: (r: ProfessionRecipe) => r.profit_day },
      cell: ({ row }) => <Money value={row.original.profit_day} /> },
    { id: "payback_days", header: "Pays back in", accessorFn: (r) => r.payback_days ?? Infinity,
      meta: { hint: "Days of crafting and selling at the expected pace to earn back the cost to learn.", csv: (r: ProfessionRecipe) => r.payback_days },
      cell: ({ row }) => row.original.payback_days === null ? <span className="muted">-</span> : `${num(row.original.payback_days, 0)} days` },
  ], [skill]);

  const set = (k: string, v: unknown) => setF((old) => ({ ...old, [k]: v }));

  if (error) return <div className="error-banner">{error}</div>;
  if (!data) return <Skeleton />;
  const anySkills = chars.some((c) => c.professions.length);

  return (
    <section>
      <div className="page-head">
        <h1>Professions</h1>
        <p className="lead">
          Each character's skill, and the recipes it could learn next: where to get them (trainer, vendor or auction
          house), the skill they need, what they make and how quickly they pay for themselves.
        </p>
      </div>

      {!anySkills && (
        <div className="warning info" style={{ marginBottom: 18 }}>
          <span>No skill levels yet. Update the addon (Settings), log in with each character, open its profession
            windows and trainers, then type <code>/reload</code>. Until then the list shows every recipe of the
            profession and marks what any of your characters has learned.</span>
        </div>
      )}

      <div className="char-grid">
        {chars.map((c) => (
          <button key={c.char_key} className={`char-card ${char?.char_key === c.char_key ? "selected" : ""}`}
            onClick={() => set("char", c.char_key)}>
            <div className="char-name" style={{ color: CLASS_COLORS[c.class ?? ""] }}>{c.name}</div>
            {c.professions.length === 0 ? <div className="muted small">No professions recorded yet</div> : c.professions.map((p) => (
              <div key={p.profession} className="skill">
                <div className="skill-head small"><span>{p.profession}</span><span className="muted">{p.rank} / {p.max_rank ?? "?"}</span></div>
                <div className="skill-bar"><div style={{ width: `${Math.min(100, (p.rank / (p.max_rank || 300)) * 100)}%` }} /></div>
              </div>
            ))}
          </button>
        ))}
      </div>

      <div className="tabs">
        {profs.map((p) => (
          <button key={p} className={p === profession ? "active" : ""} onClick={() => set("profession", p)}>{p}</button>
        ))}
      </div>

      {skill && (
        <p className="muted small">
          {char?.name}: {skill.profession} {skill.rank}/{skill.max_rank ?? "?"}, {skill.known} of {skill.recipes} recipes known
          {skill.seen_at ? `, skill seen ${ago(skill.seen_at)}` : ""}.
          {!skill.window_seen && " Open this profession's window in game so Simsar knows which recipes this character has."}
        </p>
      )}

      <div className="filters">
        <label className="check">
          <input type="checkbox" checked={f.learnableOnly} onChange={(e) => set("learnableOnly", e.target.checked)} />
          Only recipes {char?.name ?? "this character"} does not know
        </label>
        {skill && (
          <label className="check">
            <input type="checkbox" checked={f.canLearnOnly} onChange={(e) => set("canLearnOnly", e.target.checked)} />
            Only what the current skill allows
          </label>
        )}
        <span className="spacer" />
        <span className="small">{rows.length} recipes</span>
        <button onClick={() => downloadCsv(`simsar-forever-${profession.toLowerCase()}-recipes`, rows, columns)}>Export CSV</button>
      </div>

      <DataTable rows={rows} columns={columns} sorting={sorting} onSortingChange={setSorting}
        onRowClick={(r) => r.product_id && navigate(`/item/${r.product_id}`)}
        empty="No recipes here. Open this profession's window or a trainer in game, then /reload." />

      {data.vendor_recipes.length > 0 && (
        <>
          <h2 className="section-title">
            Other recipes vendors sell <Hint text="Recipes seen in vendor windows whose recipe Simsar does not know yet. Learn one and open the profession window to see its numbers." />
          </h2>
          <div className="table-wrap">
            <table className="data">
              <thead><tr><th className="left">Recipe</th><th>Vendor price</th><th>On the auction house</th><th className="left">Where</th></tr></thead>
              <tbody>
                {data.vendor_recipes.map((v) => (
                  <tr key={v.item_id}>
                    <td className="left"><Link to={`/item/${v.item_id}`}>{v.name}</Link>{v.limited ? <span className="muted small"> limited stock</span> : null}</td>
                    <td><Money value={v.price} /></td>
                    <td><Money value={v.auction_price} /></td>
                    <td className="left muted small">{[v.vendor, v.zone].filter(Boolean).join(", ")}</td>
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
