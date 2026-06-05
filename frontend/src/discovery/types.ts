/* Matchbox — Discovery domain types (SSOT for the view-model).
   Mirrors the design handoff §D3/§D4 and discovery-data.js. The backend
   (discovery_api/repo.py) serializes each scored `job` into this exact `Role`
   shape so the ported components stay byte-identical to the design prototype. */

export type FitLevel = "strong" | "good" | "stretch";
export type EligibilityStatus = "eligible" | "unclear" | "ineligible";
export type Freshness = "open" | "closing" | "closed";

/** A decision is null while undecided; `skip` is transient (never persisted as a
    decision — it sets skipped_on and the role returns tomorrow). */
export type Decision = "tracked" | "dismissed" | "tailoring" | "watch" | null;
/** What the UI can send; `skip` defers the role for today. */
export type DecisionInput = "tracked" | "dismissed" | "tailoring" | "watch" | "skip";

export interface FitRead {
  level: FitLevel;
  reason: string;
}

export interface EligibilityRead {
  status: EligibilityStatus;
  reason: string;
}

export interface Coverage {
  covered: number;
  total: number;
}

export interface Role {
  id: string;
  company: string;
  title: string;
  location: string;
  remote: boolean;
  salary: string | null; // display string, e.g. "$150–185k"; null = undisclosed
  source: string; // "Referral · Dana" / "Careers page"
  postedDaysAgo: number;
  link: string;
  fit: FitRead;
  eligibility: EligibilityRead;
  coverage: Coverage | null;
  freshness: Freshness;
  closingInDays: number | null;
  mono: { bg: string; fg: string };
  jd: string[]; // the full description split into paragraphs
  decision: Decision;
}

export interface WatchedCompany {
  company: string;
  note: string;
  status: string; // "watching" | "active"
  openRoles: number;
  mono: { bg: string; fg: string };
}
