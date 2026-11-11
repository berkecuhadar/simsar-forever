import type { ReactNode } from "react";

export function Hint({ text, children }: { text: string; children?: ReactNode }) {
  return (
    <span className="hint" tabIndex={0}>
      {children ?? <span className="hint-icon">?</span>}
      <span className="hint-bubble" role="tooltip">{text}</span>
    </span>
  );
}
