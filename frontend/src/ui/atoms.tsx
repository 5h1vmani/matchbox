/* Shared atoms — ported verbatim (markup + classNames) from designs/v1/ui.jsx.
   window.* globals swapped for ES imports; behaviour and DOM unchanged. */
import type { ReactNode } from "react";
import type { Application } from "../types";
import { STAGES, stageMeta } from "../data/stages";
import { actionPhrase, cx, dueInfo } from "../lib/derive";
import { Icon } from "./icon";

export function MonoLogo({ app, size = 34, radius = 8 }: { app: Application; size?: number; radius?: number }) {
  const initials = app.company.replace(/[^A-Za-z0-9]/g, "").slice(0, 2);
  return (
    <span
      className="mono-logo"
      style={{
        background: app.mono.bg,
        color: app.mono.fg,
        width: size,
        height: size,
        borderRadius: radius,
        fontSize: Math.round(size * 0.4),
      }}
    >
      {initials.charAt(0).toUpperCase() + (initials.charAt(1) || "")}
    </span>
  );
}

export function StageDot({ stage, size = 8 }: { stage: string; size?: number }) {
  return <span className="sdot" style={{ width: size, height: size, background: stageMeta(stage).tone }} />;
}

export function Due({ due, short }: { due: number | null | undefined; short?: boolean }) {
  const info = dueInfo(due);
  if (!info) return null;
  return (
    <span className={"due " + info.cls}>
      <Icon name={info.icon} size={11} /> {short ? info.short : info.text}
    </span>
  );
}

export function Badge({ tone = "neutral", children, dot }: { tone?: string; children: ReactNode; dot?: boolean }) {
  return <span className={cx("mbadge", "t-" + tone, dot && "has-dot")}>{children}</span>;
}

/* Stage stepper for the detail view — shows pipeline progress honestly. */
export function StageStepper({ stage }: { stage: string }) {
  const flow = STAGES.filter((s) => s.id !== "rejected");
  const closed = stage === "rejected";
  const curIdx = closed ? -1 : flow.findIndex((s) => s.id === stage);
  return (
    <div className={cx("stepper", closed && "is-closed")}>
      {flow.map((s, i) => {
        const done = !closed && i < curIdx;
        const cur = !closed && i === curIdx;
        return (
          <div key={s.id} className={cx("step", done && "done", cur && "cur")}>
            <span className="step__dot" style={cur ? { background: s.tone, borderColor: s.tone } : undefined}>
              {done && <Icon name="check" size={11} />}
            </span>
            <span className="step__lbl">{s.short}</span>
          </div>
        );
      })}
    </div>
  );
}

/* Compose the action line as JSX. */
export function ActionLine({ app }: { app: Application }) {
  const p = actionPhrase(app);
  return (
    <span>
      {p.lead}
      {p.joiner ? p.joiner : p.strong ? " " : ""}
      {p.strong && <b>{p.strong}</b>}
    </span>
  );
}
