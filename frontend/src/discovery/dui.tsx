/* Matchbox — Discovery atoms & helpers. Ported byte-identical from
   designs/v1.1/dui.jsx. The only changes: the Lucide-CDN `Icon` global becomes
   the shared lucide-react `Icon`; `dcx` becomes the shared `cx`. Every
   className, inline style, and copy string is preserved verbatim. */
import type { CSSProperties } from "react";
import { Icon } from "../ui/icon";
import { cx as dcx } from "../lib/derive";
import type { Coverage as CoverageT, EligibilityRead as EligT, FitRead, Role } from "./types";

export function MonoLogo({ role, size = 38, radius = 9 }: { role: Role; size?: number; radius?: number }) {
  const initials = role.company.replace(/[^A-Za-z0-9]/g, "").slice(0, 2);
  return (
    <span className="mono-logo" style={{ background: role.mono.bg, color: role.mono.fg, width: size, height: size, borderRadius: radius, fontSize: Math.round(size * 0.4) }}>
      {initials.charAt(0).toUpperCase() + (initials.charAt(1) || "").toLowerCase()}
    </span>
  );
}

export const FIT_META: Record<string, { dots: number; label: string; tone: string; bg: string }> = {
  strong:  { dots: 4, label: "Strong fit",  tone: "#2f6b46", bg: "#e7f5ec" },
  good:    { dots: 3, label: "Good fit",    tone: "#574747", bg: "#ede8e8" },
  stretch: { dots: 2, label: "A stretch",   tone: "#8a5a1f", bg: "#f5ead9" },
};

/* Fit read — a 4-dot meter + label + reason. Never a bare percentage. */
export function FitMeter({ fit, compact }: { fit: FitRead; compact?: boolean }) {
  const meta = FIT_META[fit.level] || FIT_META.good;
  return (
    <div className={dcx("read", "fit", compact && "compact")}>
      <div className="read__head">
        <span className="dots" aria-hidden="true">
          {[0, 1, 2, 3].map((i) => (
            <span key={i} className="dot" style={{ background: i < meta.dots ? meta.tone : "var(--zinc-200)" }} />
          ))}
        </span>
        <span className="read__label" style={{ color: meta.tone }}>{meta.label}</span>
      </div>
      {!compact && <p className="read__reason">{fit.reason}</p>}
    </div>
  );
}

export const ELIG_META: Record<string, { icon: string; label: string; tone: string }> = {
  eligible:   { icon: "check", label: "Eligible to apply", tone: "#2f6b46" },
  unclear:    { icon: "help-circle", label: "Worth checking", tone: "#8a5a1f" },
  ineligible: { icon: "minus-circle", label: "Likely not eligible", tone: "var(--muted-foreground)" },
};

/* Eligibility read — an honest fact with the reason as the point. */
export function EligibilityRead({ elig, compact }: { elig: EligT; compact?: boolean }) {
  const meta = ELIG_META[elig.status] || ELIG_META.eligible;
  return (
    <div className={dcx("read", "elig", "is-" + elig.status, compact && "compact")}>
      <div className="read__head">
        <span className="read__ic" style={{ color: meta.tone }}><Icon name={meta.icon} size={compact ? 14 : 16} /></span>
        <span className="read__label" style={{ color: meta.tone }}>{meta.label}</span>
      </div>
      {!compact && <p className="read__reason">{elig.reason}</p>}
    </div>
  );
}

/* Freshness pill. */
export function Freshness({ role, plain }: { role: Role; plain?: boolean }) {
  if (role.freshness === "closed") {
    return <span className="fresh closed"><Icon name="lock" size={11} /> Closed</span>;
  }
  if (role.freshness === "closing") {
    return <span className="fresh closing"><Icon name="clock-3" size={11} /> {"Closing in " + role.closingInDays + " days"}</span>;
  }
  const p = role.postedDaysAgo;
  const txt = p <= 0 ? "Posted today" : p === 1 ? "Posted yesterday" : "Posted " + p + " days ago";
  if (plain) return <span className="fresh open plain"><Icon name="circle" size={9} /> {txt}</span>;
  return <span className="fresh open">{txt}</span>;
}

export function Coverage({ coverage, compact }: { coverage: CoverageT | null; compact?: boolean }) {
  if (!coverage) return null;
  const pct = Math.round((coverage.covered / coverage.total) * 100);
  return (
    <div className={dcx("cov", compact && "compact")}>
      <div className="cov__top">
        <span className="cov__lbl">CV covers {coverage.covered} of {coverage.total} must-haves</span>
        {!compact && <span className="cov__pct mono">{pct}%</span>}
      </div>
      <div className="cov__track"><div className="cov__fill" style={{ width: pct + "%" }} /></div>
    </div>
  );
}

export function fullLoc(role: Role): string {
  if (role.remote) {
    const where = role.location.replace(/remote/i, "").replace(/[()]/g, "").trim();
    return "Remote" + (where ? " · " + where : "");
  }
  return role.location;
}

export { dcx, Icon };
export type { CSSProperties };
