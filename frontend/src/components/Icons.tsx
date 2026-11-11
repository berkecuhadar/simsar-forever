import { useState } from "react";

// Item quality colours as the game uses them.
export const QUALITY_COLORS: Record<number, string> = {
  0: "#9d9d9d", 1: "#ffffff", 2: "#1eff00", 3: "#0070dd", 4: "#a335ee", 5: "#ff8000",
};

let coinsWork = true;

export function Coin({ kind }: { kind: "gold" | "silver" | "copper" }) {
  const [ok, setOk] = useState(coinsWork);
  if (!ok) return <i>{kind[0]}</i>;
  return (
    <img className="coin-icon" src={`/api/icons/coin/${kind}.jpg`} alt={kind[0]}
      onError={() => { coinsWork = false; setOk(false); }} />
  );
}

export function ItemIcon({ id, quality, size = 20 }: { id: number | null | undefined; quality?: number | null; size?: number }) {
  const [ok, setOk] = useState(true);
  const border = quality !== null && quality !== undefined ? QUALITY_COLORS[quality] : "#3a4150";
  if (!id || !ok) return <span className="item-icon empty" style={{ width: size, height: size, borderColor: border }} />;
  return (
    <img className="item-icon" src={`/api/icons/${id}.jpg`} width={size} height={size} loading="lazy" alt=""
      style={{ borderColor: border }} onError={() => setOk(false)} />
  );
}

export function ItemName({ name, quality }: { name: string; quality?: number | null }) {
  const color = quality !== null && quality !== undefined && quality !== 1 ? QUALITY_COLORS[quality] : undefined;
  return <span style={color ? { color } : undefined}>{name}</span>;
}
