export type Flag =
  | "stale" | "no_volume" | "thin_volume" | "bubble" | "cheap"
  | "possible_misprice" | "not_live" | "low_confidence" | "no_vendor_price";

export type Label = "fast_profitable" | "fast_thin" | "slow_profitable" | "avoid" | "unknown";

export interface Item {
  item_id: number;
  name: string;
  groups: string[];
  group: string | null;
  price_now: number | null;
  price_src: "auctionator" | "tsm_min_buyout" | "tsm_market" | null;
  market: number | null;
  historical: number | null;
  sell_price: number | null;
  sell_ref: number | null;
  net_sell: number | null;
  sale_rate: number | null;
  sold_per_day_region: number | null;
  my_sales_per_day: number | null;
  available: number | null;
  turnover_day: number | null;
  income_day: number | null;
  flip_profit: number | null;
  flip_margin: number | null;
  flip_profit_day: number | null;
  volatility: number | null;
  trend: number | null;
  reference: number | null;
  disc_ref: number | null;
  disc_hist: number | null;
  period_min: number | null;
  period_max: number | null;
  n_points: number | null;
  confidence: number;
  score: number | null;
  label: Label;
  flags: Flag[];
  deposit: number | null;
  vendor_sell: number | null;
  data_age_h: number | null;
}

export interface ItemFull extends Item {
  min_buyout: number | null;
  market_realm: number | null;
  market_region: number | null;
  avg_sale: number | null;
  sold_per_day_realm: number | null;
  listings_per_sale: number;
  period_median: number | null;
  n_days: number | null;
  pctile: number | null;
  bubble_ratio: number | null;
  price_age_h: number | null;
}

export interface Reagent {
  item_id: number | null;
  name: string;
  count: number;
  unit_price: number | null;
  price_src: "auction" | "vendor" | null;
  unit_net_sell: number | null;
}

export type Verdict = "craft" | "own_mats" | "sell_mats" | "missing" | "no_product";

export interface Craft {
  recipe_key: string;
  profession: string;
  name: string;
  source: string;
  learned: number | null;
  product_id: number | null;
  product_name: string;
  yield: number;
  reagents: Reagent[];
  missing: string[];
  cost_buy: number | null;
  mats_value: number | null;
  revenue: number | null;
  profit: number | null;
  profit_vs_mats: number | null;
  roi: number | null;
  crafts_per_day: number | null;
  profit_day: number | null;
  product_sales_per_day: number | null;
  product_price: number | null;
  product_flags: Flag[];
  recipe_item?: { item_id: number; name: string; price: number | null };
  payback_days?: number;
  verdict: Verdict;
}

export interface Group {
  key: string;
  title: string;
  profession: string;
  role: "gather" | "craft" | "recipe";
  color: string;
  mine?: boolean;
}

export interface Brief {
  item_id: number;
  name: string;
  value: number;
  label: Label;
  price_now: number | null;
  flags: Flag[];
}

export interface GroupOverview extends Group {
  items: number;
  with_volume: number;
  turnover_day: number;
  recipes: number;
  profitable_crafts: number;
  top_flips: Brief[];
  top_sellers: Brief[];
  top_crafts: { recipe_key: string; name: string; profit: number | null; profit_day: number | null; product_id: number | null }[];
}

export interface Source {
  key: string;
  label: string;
  ok: boolean;
  updated_at?: number | null;
  age_h?: number | null;
  checked_at?: number | null;
  error?: string | null;
  url?: string | null;
  path?: string | null;
  imported_at?: number | null;
  file_mtime?: number | null;
  last_full_scan?: number | null;
  addon_version?: string | null;
  items?: number | null;
  present?: boolean;
  recipes?: number | null;
  invoices?: number | null;
}

export interface Status {
  version: string;
  demo: boolean;
  now: number;
  sources: Source[];
  warnings: { level: "demo" | "error" | "warn" | "info"; message: string }[];
  fees: { ah_cut: number; cut_source: string; deposit_rate: number; deposit_source: string; auction_hours: number; max_relists: number };
  assumptions: {
    realm_share: number; market_share: number; sell_price: string; history_days: number;
    good_margin: number; fast_sales_per_day: number; stale_hours: number; tsm: string; reference_price: string;
  };
  alerts_unseen: number;
  items: number;
  tracked_items: number;
  recipes: number;
  built_at: number;
  build_seconds: number;
  configured: boolean;
  realm_label: string;
}

export interface Install {
  path: string;
  exists: boolean;
  is_forever: boolean;
  flavor: string | null;
  has_wtf: boolean;
  auctionator_version: string | null;
  simsar_export_installed: boolean;
  accounts: { name: string; has_auctionator: boolean; auctionator_mtime: number | null; has_simsar_export: boolean }[];
  auctionator_realms?: { key: string; items: number }[];
}

export interface SetupInfo {
  config_exists: boolean;
  current: { region: string; realm: string | null; game_dir: string | null; account: string | null;
    auctionator_realm: string | null; professions: string[] };
  catalog: { regions: { key: string; label: string; realms: string[] }[]; realm_types: Record<string, string>;
    factions: Record<string, string> };
  professions: string[];
  installs: Install[];
}

export interface Alert {
  id: number;
  created_at: number;
  kind: string;
  item_id: number | null;
  title: string;
  message: string;
  seen: number;
}

export interface ItemDetail {
  item: ItemFull;
  explanation: string[];
  history: {
    realm: { t: number; market: number | null; min_buyout: number | null; historical: number | null }[];
    region: { t: number; market: number | null; avg_sale: number | null; sale_rate: number | null; sold_per_day: number | null }[];
    auctionator: { t: number; low: number; high: number; available: number | null }[];
    postings: { t: number; price: number; quantity: number }[];
  };
  crafts: Craft[];
}

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path);
  if (!r.ok) throw new Error(`${path}: HTTP ${r.status}`);
  return r.json();
}

export const api = {
  status: () => get<Status>("/api/status"),
  overview: () => get<{ groups: GroupOverview[] }>("/api/overview"),
  groups: () => get<Group[]>("/api/groups"),
  items: (scope: "tracked" | "all" = "tracked") => get<Item[]>(`/api/items?scope=${scope}`),
  item: (id: number) => get<ItemDetail>(`/api/items/${id}`),
  crafts: () => get<Craft[]>("/api/crafts"),
  alerts: () => get<Alert[]>("/api/alerts"),
  markSeen: () => fetch("/api/alerts/seen", { method: "POST" }),
  refresh: () => fetch("/api/refresh", { method: "POST" }).then((r) => r.json()),
  setup: () => get<SetupInfo>("/api/setup"),
  setupInspect: (path: string, account?: string) =>
    get<Install>(`/api/setup/inspect?path=${encodeURIComponent(path)}${account ? `&account=${encodeURIComponent(account)}` : ""}`),
  setupCheck: (region: string, realm: string | null) =>
    get<Record<string, { ok: boolean; status: number | null; rate_limited?: boolean }>>(
      `/api/setup/check?region=${region}${realm ? `&realm=${realm}` : ""}`),
  setupSave: async (body: object) => {
    const r = await fetch("/api/setup", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    if (!r.ok) throw new Error((await r.json()).detail ?? `HTTP ${r.status}`);
    return r.json();
  },
};
