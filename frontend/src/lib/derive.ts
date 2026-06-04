/* Read-only derivations — the calm logic that makes the UI feel right.
   Ported verbatim from designs/v1 (ui.jsx, Today.jsx, store.jsx §07). These are
   recomputed on read and never persisted (design handoff §07). SSOT for the
   client; the backend persists only raw facts. */
import type { Application, EventKind } from "../types";

/** classnames join: truthy parts only. */
export function cx(...parts: Array<string | false | null | undefined>): string {
  return parts.filter(Boolean).join(" ");
}

export interface DueInfo {
  cls: string;
  text: string;
  short: string;
  icon: string;
}

/** due: integer days from today (neg = overdue, 0 = today), or null. */
export function dueInfo(due: number | null | undefined): DueInfo | null {
  if (due === null || due === undefined) return null;
  if (due < 0) return { cls: "over", text: -due + "d overdue", short: -due + "d late", icon: "alert-circle" };
  if (due === 0) return { cls: "today", text: "Today", short: "Today", icon: "circle-dot" };
  if (due === 1) return { cls: "soon", text: "Tomorrow", short: "Tmrw", icon: "clock-3" };
  if (due <= 6) return { cls: "soon", text: "in " + due + " days", short: due + "d", icon: "clock-3" };
  return { cls: "later", text: "in " + due + " days", short: due + "d", icon: "clock-3" };
}

export function updatedText(days: number): string {
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  return days + "d ago";
}

export function appliedText(days: number | null | undefined): string {
  if (days === null || days === undefined) return "Not applied";
  if (days === 0) return "Applied today";
  if (days === 1) return "Applied yesterday";
  return "Applied " + days + "d ago";
}

export interface Phrase {
  lead: string;
  sub?: string | null;
  strong?: string;
  joiner?: string;
  plain?: boolean;
  offer?: boolean;
}

/** Human verb for an action kind (drives the action line on every surface). */
export function actionPhrase(app: Application): Phrase {
  const a = app.nextAction;
  if (!a) return { lead: "No action needed", sub: null, plain: true };
  switch (a.kind) {
    case "interview":
      return { lead: a.label, strong: app.company, joiner: " with ", sub: app.role + (a.time ? " · " + a.time : "") };
    case "offer":
      return { lead: "Respond to " + app.company, sub: app.role + " · " + app.salary, offer: true };
    case "apply":
      return { lead: "Apply to", strong: app.company, sub: app.role };
    case "followup":
      return { lead: "Follow up with", strong: app.company, sub: app.role };
    case "prep":
      return { lead: "Prep for", strong: app.company, sub: app.role };
    case "thanks":
      return { lead: "Send thank-you to", strong: app.company, sub: app.role };
    case "wait":
      return { lead: "Waiting to hear back", sub: app.company + " · " + app.role, plain: true };
    default:
      return { lead: a.label, sub: app.role };
  }
}

/** Lucide icon name for a timeline event kind. */
export function eventIcon(kind: EventKind | string): string {
  const map: Record<string, string> = {
    saved: "bookmark", applied: "send", reply: "mail", screen: "phone",
    onsite: "users", offer: "party-popper", rejected: "x-circle",
    note: "sticky-note", followup: "reply", advanced: "arrow-right", thanks: "heart",
  };
  return map[kind] || "circle";
}

/** Sort key for "what is due" — most overdue first; no date sinks to the end. */
export function dueVal(a: Application): number {
  return a.nextAction && a.nextAction.due !== null ? a.nextAction.due : 999;
}

/** Kind ranking for the Today list (time-sensitive first). */
export const RANK: Record<string, number> = {
  interview: 0, offer: 0, thanks: 1, prep: 1, apply: 2, followup: 2, wait: 9,
};

/** Staleness ("going cold") — derived, never persisted (handoff §07). */
export function isStale(a: Application): boolean {
  const active = a.stage === "applied" || a.stage === "phone" || a.stage === "onsite";
  const imminent = !!(a.nextAction && a.nextAction.due !== null && a.nextAction.due <= 3);
  return active && !imminent && a.updatedDaysAgo >= 11;
}
