import type { Flag, Label, Verdict } from "../api";
import { FLAGS, FLAG_HINTS, LABELS, LABEL_HINTS, VERDICTS, VERDICT_HINTS } from "../strings";
import { Hint } from "./Hint";

const QUIET: Flag[] = ["not_live", "low_confidence"];

export function LabelBadge({ label }: { label: Label }) {
  return (
    <Hint text={LABEL_HINTS[label]} plain>
      <span className={`badge label-${label}`}>{LABELS[label]}</span>
    </Hint>
  );
}

export function VerdictBadge({ verdict }: { verdict: Verdict }) {
  return (
    <Hint text={VERDICT_HINTS[verdict]} plain>
      <span className={`badge verdict-${verdict}`}>{VERDICTS[verdict]}</span>
    </Hint>
  );
}

export function Flags({ flags, all = false }: { flags: Flag[]; all?: boolean }) {
  const shown = all ? flags : flags.filter((f) => !QUIET.includes(f));
  if (!shown.length) return null;
  return (
    <span className="flags">
      {shown.map((f) => (
        <Hint key={f} text={FLAG_HINTS[f]} plain>
          <span className={`flag flag-${f}`}>{FLAGS[f]}</span>
        </Hint>
      ))}
    </span>
  );
}
