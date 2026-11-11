export function Money({ value, signed = false }: { value: number | null | undefined; signed?: boolean }) {
  if (value === null || value === undefined || Number.isNaN(value)) return <span className="muted">-</span>;
  const neg = value < 0;
  let c = Math.round(Math.abs(value));
  const g = Math.floor(c / 10000);
  c -= g * 10000;
  const s = Math.floor(c / 100);
  c -= s * 100;
  const parts: JSX.Element[] = [];
  if (g) parts.push(<span key="g" className="coin gold">{g.toLocaleString("en-US")}<i>g</i></span>);
  if (s || (g && c)) parts.push(<span key="s" className="coin silver">{g ? String(s).padStart(2, "0") : s}<i>s</i></span>);
  if (!g && (c || !parts.length)) parts.push(<span key="c" className="coin copper">{s ? String(c).padStart(2, "0") : c}<i>c</i></span>);
  return (
    <span className={`money ${signed ? (neg ? "neg" : "pos") : ""}`}>
      {neg ? "-" : signed ? "+" : ""}
      {parts}
    </span>
  );
}

export function moneyText(value: number | null | undefined): string {
  if (value === null || value === undefined) return "-";
  const neg = value < 0;
  let c = Math.round(Math.abs(value));
  const g = Math.floor(c / 10000);
  c -= g * 10000;
  const s = Math.floor(c / 100);
  c -= s * 100;
  const out = [g ? `${g.toLocaleString("en-US")}g` : "", s ? `${s}s` : "", !g && (c || !s) ? `${c}c` : ""].filter(Boolean);
  return (neg ? "-" : "") + out.join(" ");
}

export function pct(v: number | null | undefined, digits = 0, signed = false): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "-";
  const s = (v * 100).toFixed(digits) + "%";
  return signed && v > 0 ? "+" + s : s;
}

export function num(v: number | null | undefined, digits = 1): string {
  if (v === null || v === undefined || Number.isNaN(v)) return "-";
  if (Math.abs(v) >= 1000) return Math.round(v).toLocaleString("en-US");
  return v.toFixed(digits);
}

export function ago(ts: number | null | undefined, now = Date.now() / 1000): string {
  if (!ts) return "never";
  const s = Math.max(0, now - ts);
  if (s < 90) return "just now";
  if (s < 5400) return `${Math.round(s / 60)} min ago`;
  if (s < 172800) return `${Math.round(s / 3600)} h ago`;
  return `${Math.round(s / 86400)} days ago`;
}

export function dateTime(ts: number | null | undefined): string {
  if (!ts) return "-";
  return new Date(ts * 1000).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}
