import type { ColumnDef } from "@tanstack/react-table";
import type { Group, Item } from "../api";
import { Flags, LabelBadge } from "../components/Badges";
import { groupColor, groupTitle } from "../context";
import { Money, num, pct } from "../format";
import { COLUMNS, FLAGS, LABELS, PRICE_SOURCES } from "../strings";

type Key = keyof Item;

const MONEY: Key[] = ["price_now", "market", "reference", "historical", "sell_ref", "sell_price", "net_sell", "turnover_day", "income_day",
  "flip_profit", "flip_profit_day", "score", "period_min", "period_max", "deposit"];

function sortNullsLast(a: number | null, b: number | null) {
  if (a === null && b === null) return 0;
  if (a === null) return -1;
  if (b === null) return 1;
  return a - b;
}

export function itemColumns(keys: Key[], groups: Group[]): ColumnDef<Item, unknown>[] {
  return keys.map((key): ColumnDef<Item, unknown> => {
    const info = COLUMNS[key] ?? { title: key, hint: "" };
    const base = { id: key, header: info.title, accessorFn: (r: Item) => r[key] };
    if (key === "name") {
      return {
        ...base,
        meta: { hint: info.hint, align: "left", csv: (r: Item) => r.name },
        sortingFn: (a, b) => a.original.name.localeCompare(b.original.name),
        cell: ({ row }) => (
          <span className="item-name">
            <span className="swatch" style={{ background: groupColor(groups, row.original.group) }} />
            {row.original.name}
          </span>
        ),
      };
    }
    if (key === "group") {
      return { ...base, meta: { hint: info.hint, align: "left", csv: (r: Item) => groupTitle(groups, r.group) },
        cell: ({ row }) => <span className="muted">{groupTitle(groups, row.original.group)}</span> };
    }
    if (key === "label") {
      return { ...base, meta: { hint: info.hint, align: "left", csv: (r: Item) => LABELS[r.label] },
        cell: ({ row }) => <LabelBadge label={row.original.label} /> };
    }
    if (key === "flags") {
      return { ...base, enableSorting: false,
        meta: { hint: info.hint, align: "left", csv: (r: Item) => r.flags.map((f) => FLAGS[f]).join("; ") },
        cell: ({ row }) => <Flags flags={row.original.flags} /> };
    }
    const numeric = {
      ...base,
      sortingFn: (a: { original: Item }, b: { original: Item }) =>
        sortNullsLast(a.original[key] as number | null, b.original[key] as number | null),
    };
    if (key === "price_now") {
      return { ...numeric, meta: { hint: info.hint, csv: (r: Item) => r.price_now },
        cell: ({ row }) => (
          <span title={row.original.price_src ? PRICE_SOURCES[row.original.price_src] : ""}>
            <Money value={row.original.price_now} />
            {row.original.price_src !== "auctionator" && <span className="src-dot" />}
          </span>
        ) };
    }
    if (MONEY.includes(key)) {
      const signed = key === "flip_profit" || key === "flip_profit_day";
      return { ...numeric, meta: { hint: info.hint, csv: (r: Item) => (r[key] as number | null) },
        cell: ({ row }) => <Money value={row.original[key] as number | null} signed={signed} /> };
    }
    if (["sale_rate", "flip_margin", "volatility", "trend", "disc_ref", "disc_hist", "confidence"].includes(key)) {
      const signed = key === "trend" || key === "disc_ref" || key === "disc_hist" || key === "flip_margin";
      const digits = key === "trend" ? 1 : 0;
      return { ...numeric, meta: { hint: info.hint, csv: (r: Item) => (r[key] as number | null) },
        cell: ({ row }) => {
          const v = row.original[key] as number | null;
          const cls = signed && v !== null ? (v < 0 ? "neg" : v > 0 ? "pos" : "") : "";
          return <span className={cls}>{pct(v, digits, signed)}</span>;
        } };
    }
    const digits = key === "available" ? 0 : 1;
    return { ...numeric, meta: { hint: info.hint, csv: (r: Item) => (r[key] as number | null) },
      cell: ({ row }) => num(row.original[key] as number | null, digits) };
  });
}
