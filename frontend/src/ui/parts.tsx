/* Shared interactive parts — ported verbatim (markup + classNames) from
   designs/v1/parts.jsx: quick-action menu, star, pipeline views. */
import { type RefObject, useEffect, useRef, useState } from "react";
import type { Application, Flash, OpenDetail, TrackerActions } from "../types";
import { FLOW, STAGES, stageLabel } from "../data/stages";
import { cx } from "../lib/derive";
import { Icon } from "./icon";
import { StageDot } from "./atoms";

export function useOutside(ref: RefObject<HTMLElement | null>, onClose: () => void) {
  useEffect(() => {
    const onDown = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) onClose();
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
}

interface QuickMenuProps {
  app: Application;
  actions: TrackerActions;
  flash: Flash;
  onOpen: OpenDetail;
  onClose: () => void;
  up?: boolean;
}

/* The quick-action popover — advance, log response, remind, note, close.
   Same menu used on list rows, board cards, today rows. */
export function QuickMenu({ app, actions, flash, onOpen, onClose, up }: QuickMenuProps) {
  const ref = useRef<HTMLDivElement>(null);
  useOutside(ref, onClose);
  const i = FLOW.indexOf(app.stage);
  const nextStage = i >= 0 && i < FLOW.length - 1 ? FLOW[i + 1] : null;

  const act = (fn: () => void, msg?: string) => {
    fn();
    if (msg) flash(msg);
    onClose();
  };

  return (
    <div className={cx("menu", up && "up")} ref={ref} onClick={(e) => e.stopPropagation()}>
      {nextStage && (
        <button className="mitem" onClick={() => act(() => actions.advanceStage(app.id), "Moved to " + stageLabel(nextStage).toLowerCase())}>
          <Icon name="arrow-right" size={15} /> Move to {stageLabel(nextStage).toLowerCase()}
        </button>
      )}
      <div className="menu__sec">Log a response</div>
      <button className="mitem" onClick={() => act(() => actions.logResponse(app.id, "reply"), "Logged a reply from " + app.company)}>
        <Icon name="mail-check" size={15} /> Heard back
      </button>
      <button className="mitem" onClick={() => act(() => actions.logResponse(app.id, "rejected"), app.company + " marked closed")}>
        <Icon name="x-circle" size={15} /> Rejected
      </button>
      <button className="mitem" onClick={() => act(() => actions.logResponse(app.id, "ghosted"), "Marked as no response")}>
        <Icon name="ghost" size={15} /> No response
      </button>
      <div className="menu__div" />
      <div className="menu__sec">Remind me</div>
      <button className="mitem" onClick={() => act(() => actions.remind(app.id, 0), "Reminder set for today")}>
        <Icon name="bell" size={15} /> Today
      </button>
      <button className="mitem" onClick={() => act(() => actions.remind(app.id, 3), "Reminder set for in 3 days")}>
        <Icon name="bell" size={15} /> In 3 days <span className="k">3d</span>
      </button>
      <button className="mitem" onClick={() => act(() => actions.remind(app.id, 7), "Reminder set for next week")}>
        <Icon name="bell" size={15} /> Next week <span className="k">7d</span>
      </button>
      <div className="menu__div" />
      <button className="mitem" onClick={() => { onClose(); onOpen(app, "note"); }}>
        <Icon name="sticky-note" size={15} /> Add a note
      </button>
      <button className="mitem" onClick={() => { onClose(); onOpen(app); }}>
        <Icon name="panel-right-open" size={15} /> Open details
      </button>
    </div>
  );
}

interface QuickButtonProps {
  app: Application;
  actions: TrackerActions;
  flash: Flash;
  onOpen: OpenDetail;
  up?: boolean;
  className?: string;
}

/* A button that toggles a QuickMenu. */
export function QuickButton({ app, actions, flash, onOpen, up, className }: QuickButtonProps) {
  const [open, setOpen] = useState(false);
  return (
    <span className="menu-wrap">
      <button
        className={cx("iconbtn", className)}
        title="Quick actions"
        onClick={(e) => { e.stopPropagation(); setOpen((v) => !v); }}
      >
        <Icon name="more-horizontal" size={17} />
      </button>
      {open && <QuickMenu app={app} actions={actions} flash={flash} onOpen={onOpen} onClose={() => setOpen(false)} up={up} />}
    </span>
  );
}

export function StarBtn({ app, actions, size = 15 }: { app: Application; actions: TrackerActions; size?: number }) {
  return (
    <button
      className={cx("iconbtn", app.starred && "on")}
      title={app.starred ? "Unstar" : "Star"}
      onClick={(e) => { e.stopPropagation(); actions.toggleStar(app.id); }}
    >
      <span className={cx("star", app.starred && "on")}>
        <Icon name="star" size={size} style={app.starred ? { fill: "#c79a3b" } : {}} />
      </span>
    </button>
  );
}

interface PipeProps {
  counts: Record<string, number>;
  total?: number;
  active: string;
  onPick: (id: string) => void;
}

/* ---- Pipeline: chips (compact filter row) ---- */
export function PipeChips({ counts, total, active, onPick }: PipeProps) {
  return (
    <div className="pipe-chips">
      <button className={cx("stagechip", active === "all" && "active")} onClick={() => onPick("all")}>
        All <span className="c mono">{total}</span>
      </button>
      {STAGES.map((s) => (
        <button key={s.id} className={cx("stagechip", active === s.id && "active")} onClick={() => onPick(s.id)}>
          <StageDot stage={s.id} /> {s.label} <span className="c mono">{counts[s.id] || 0}</span>
        </button>
      ))}
    </div>
  );
}

/* ---- Pipeline: proportional segmented bar + legend (ledger) ---- */
export function PipeBar({ counts, total, active, onPick }: PipeProps) {
  return (
    <div className="pipebar">
      <div className="pipebar__track">
        {STAGES.map((s) => {
          const n = counts[s.id] || 0;
          if (!n) return null;
          return (
            <div
              key={s.id}
              className="pipebar__seg"
              title={s.label + ": " + n}
              onClick={() => onPick(active === s.id ? "all" : s.id)}
              style={{ flex: n, background: s.tone, opacity: active === "all" || active === s.id ? 1 : 0.32 }}
            />
          );
        })}
      </div>
      <div className="pipebar__legend">
        <button className={cx("pipebar__key", active === "all" && "active")} onClick={() => onPick("all")}>
          <span className="c">{total}</span> <span className="k">in pipeline</span>
        </button>
        {STAGES.map((s) => (
          <button key={s.id} className={cx("pipebar__key", active === s.id && "active")} onClick={() => onPick(active === s.id ? "all" : s.id)}>
            <StageDot stage={s.id} /> <span className="k">{s.label}</span> <span className="c">{counts[s.id] || 0}</span>
          </button>
        ))}
      </div>
    </div>
  );
}

/* ---- Pipeline: funnel bars (focus) ---- */
export function Funnel({ counts, active, onPick }: PipeProps) {
  const max = Math.max(1, ...STAGES.map((s) => counts[s.id] || 0));
  return (
    <div className="funnel">
      {STAGES.map((s) => {
        const n = counts[s.id] || 0;
        const pct = Math.round((n / max) * 100);
        return (
          <div key={s.id} className={cx("frow", active === s.id && "active")} onClick={() => onPick(active === s.id ? "all" : s.id)}>
            <div className="fl"><StageDot stage={s.id} /> {s.label}</div>
            <div className="fbar-wrap">
              <div className="fbar" style={{ width: Math.max(pct, n ? 6 : 0) + "%", background: s.tone, opacity: active === "all" || active === s.id ? 1 : 0.4 }} />
            </div>
            <div className="fc">{n}</div>
          </div>
        );
      })}
    </div>
  );
}
