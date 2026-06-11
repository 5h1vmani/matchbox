/* Matchbox tracker — domain types (SSOT for the view-model).
   Mirrors the design handoff §05. The API client (api/client.ts) adapts the
   persisted DB shape (ISO timestamps) into these relative `daysAgo` view types
   so the ported components stay byte-identical to the design prototype. */

export type StageId = "saved" | "applied" | "phone" | "onsite" | "offer" | "rejected";

export interface Stage {
  id: StageId;
  label: string;
  short: string;
  tone: string; // hex; the stage's dot/bar colour
}

export type ActionKind =
  | "apply" | "followup" | "interview" | "prep" | "thanks" | "offer" | "wait";

export interface NextAction {
  kind: ActionKind;
  label: string;
  due: number | null; // days from today: <0 overdue, 0 today, null = no date
  time?: string; // "13:30" for interviews
  deadline?: number; // offer response window (informational)
}

export type EventKind =
  | "saved" | "applied" | "reply" | "screen" | "onsite"
  | "offer" | "rejected" | "note" | "advanced" | "followup";

export interface TimelineEvent {
  daysAgo: number;
  kind: EventKind;
  text: string;
}

export interface Contact {
  name: string;
  role: string;
  initials: string;
}

export interface Note {
  daysAgo: number;
  text: string;
}

export interface Application {
  id: string;
  company: string;
  role: string;
  location: string;
  salary: string; // display string, e.g. "$150–185k"
  source: string; // "Referral · Dana"
  stage: StageId;
  appliedDaysAgo: number | null; // null while still 'saved'
  updatedDaysAgo: number; // drives staleness + "last update"
  nextAction: NextAction | null;
  hasDraft: boolean;
  events: TimelineEvent[];
  contacts: Contact[];
  notes: Note[];
  starred: boolean;
  mono: { bg: string; fg: string }; // monogram colours
  stale: boolean; // DERIVED — recomputed on read, never persisted
  jobId: number; // the job row this application tracks
  runId: string | null; // tailoring run queued for this app (null = never queued)
  jobUrl: string | null; // apply_url ?? url from the job row
  cvUrl: string | null; // served CV link when a tailored PDF exists on disk
}

export interface Profile {
  name: string;
  file: string;
  initials: string;
}

export type ResponseType = "reply" | "rejected" | "ghosted";

/** UI helper types shared by the screens. */
export type Flash = (msg: string) => void;
export type OpenDetail = (app: Application, mode?: string) => void;
export type Direction = "ledger" | "focus";

/** The inline action contract shared by every surface (design handoff §06). */
export interface TrackerActions {
  advanceStage(id: string): void;
  setStage(id: string, stage: StageId): void;
  snooze(id: string, days?: number): void;
  remind(id: string, days: number): void;
  markDone(id: string): void;
  logResponse(id: string, type: ResponseType): void;
  addNote(id: string, text: string): void;
  toggleStar(id: string): void;
}
