import { useEffect, useState } from "react";

type Kind = "info" | "success" | "error";
interface Toast { id: number; text: string; kind: Kind }

const EVENT = "simsar-forever-toast";
let nextId = 1;

// Callable from anywhere, including plain functions like the CSV export.
export function toast(text: string, kind: Kind = "info") {
  window.dispatchEvent(new CustomEvent(EVENT, { detail: { id: nextId++, text, kind } }));
}

export function Toasts() {
  const [items, setItems] = useState<Toast[]>([]);
  useEffect(() => {
    const onToast = (e: Event) => {
      const t = (e as CustomEvent<Toast>).detail;
      setItems((old) => [...old.slice(-3), t]);
      setTimeout(() => setItems((old) => old.filter((x) => x.id !== t.id)), t.kind === "error" ? 8000 : 4000);
    };
    window.addEventListener(EVENT, onToast);
    return () => window.removeEventListener(EVENT, onToast);
  }, []);
  return (
    <div className="toasts" role="status" aria-live="polite">
      {items.map((t) => (
        <div key={t.id} className={`toast ${t.kind}`}>
          <span>{t.text}</span>
          <button aria-label="Dismiss" onClick={() => setItems((old) => old.filter((x) => x.id !== t.id))}>×</button>
        </div>
      ))}
    </div>
  );
}

export function Skeleton({ rows = 8 }: { rows?: number }) {
  return (
    <div className="skeleton" aria-busy="true" aria-label="Loading">
      {Array.from({ length: rows }, (_, i) => <div key={i} className="skeleton-row" />)}
    </div>
  );
}
