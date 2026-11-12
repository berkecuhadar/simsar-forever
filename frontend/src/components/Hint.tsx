import type { ReactNode } from "react";

// With children the term itself gets a dotted underline; without, a small "i" marker is shown.
export function Hint({ text, children, plain = false }: { text: string; children?: ReactNode; plain?: boolean }) {
  return (
    <span className="hint" tabIndex={0}>
      {children !== undefined
        ? <span className={plain ? undefined : "hint-term"}>{children}</span>
        : <span className="hint-icon">i</span>}
      <span className="hint-bubble" role="tooltip">{text}</span>
    </span>
  );
}
