/* SetupRail — the persistent onboarding progress rail ("Step N of 7").
   A slim horizontal strip the Shell renders above screen content until every
   step is done: done = check + muted, active = highlighted with the full
   "Step N of 7: <label>", upcoming = dim. Every step is clickable and jumps to
   the screen where that step happens (nav ids from Shell's NAV registry). */
import type { SetupStep } from "../api/setup";
import { cx } from "../lib/derive";
import { Icon } from "./icon";

// step id -> Shell nav id. Targets live on the Profile screen (one row, edited
// under "Targets & work authorization"); jobs arrive via Sources (paste/scan);
// tailoring starts from Discover's review queue; applying is logged in the
// applications tracker.
const STEP_NAV: Record<string, string> = {
  history: "onboarding",
  verify: "verify",
  profile: "profile",
  targets: "profile",
  job: "sources",
  tailor: "review",
  apply: "applications",
};

export function SetupRail({ steps, current, onGo }: {
  steps: SetupStep[];
  current: number;
  onGo: (navId: string) => void;
}) {
  return (
    <nav className="setuprail" aria-label="Setup progress">
      {steps.map((s, i) => (
        <button
          key={s.id}
          className={cx("setuprail__step", s.done && "done", s.active && "active")}
          title={s.done ? `${s.label} — done` : `Step ${i + 1} of ${steps.length}: ${s.label}`}
          onClick={() => onGo(STEP_NAV[s.id] ?? "today")}
        >
          <span className="setuprail__dot" aria-hidden="true">
            {s.done ? <Icon name="check" size={11} strokeWidth={2.5} /> : i + 1}
          </span>
          <span className="setuprail__lbl">
            {s.active ? `Step ${current + 1} of ${steps.length}: ${s.label}` : s.label}
            {s.active && s.partial && <em className="setuprail__part"> — in progress</em>}
          </span>
        </button>
      ))}
    </nav>
  );
}
