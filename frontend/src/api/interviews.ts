/* Interviews API client — the manual interview-loop log. Rounds are entered by
   hand (there is no calendar / ATS / email sync); the server returns the exact
   `Round` view-model with an inlined `debrief`, so the screen renders it
   unchanged. Every call is wrapped: reads fall back to an empty list, writes
   fall back to null so the UI can leave the row untouched on failure. */

export type RoundKind = "recruiter" | "hm" | "technical" | "onsite" | "values" | "other";
export type RoundStatus = "scheduled" | "done" | "cancelled";
export type DebriefSentiment = "good" | "mixed" | "tough" | "unknown";

export interface Debrief {
  sentiment: DebriefSentiment | null;
  notes: string | null;
  createdAt: string;
}

export interface Round {
  id: number;
  applicationId: number;
  kind: RoundKind | string;
  scheduledAt: string | null;
  status: RoundStatus | string;
  focus: string | null;
  debrief: Debrief | null;
}

export interface RoundCreate {
  kind: RoundKind | string;
  scheduledAt?: string | null;
  focus?: string | null;
  status?: RoundStatus | string;
}

export interface RoundPatch {
  kind?: RoundKind | string;
  scheduledAt?: string | null;
  focus?: string | null;
  status?: RoundStatus | string;
}

export interface DebriefCreate {
  sentiment?: DebriefSentiment | string;
  notes?: string | null;
}

const JSON_HEADERS = { "Content-Type": "application/json" };

async function getJSON<T>(url: string, fallback: T): Promise<T> {
  try {
    const r = await fetch(url);
    return r.ok ? ((await r.json()) as T) : fallback;
  } catch {
    return fallback;
  }
}

async function sendJSON(url: string, method: string, body?: unknown): Promise<Round | null> {
  try {
    const r = await fetch(url, {
      method,
      headers: JSON_HEADERS,
      body: body ? JSON.stringify(body) : undefined,
    });
    return r.ok ? ((await r.json()) as Round) : null;
  } catch {
    return null;
  }
}

export const listRounds = (appId: string) =>
  getJSON<Round[]>(`/api/applications/${appId}/rounds`, []);

export const createRound = (appId: string, body: RoundCreate) =>
  sendJSON(`/api/applications/${appId}/rounds`, "POST", body);

export const updateRound = (id: number, body: RoundPatch) =>
  sendJSON(`/api/rounds/${id}`, "PATCH", body);

export const captureDebrief = (id: number, body: DebriefCreate) =>
  sendJSON(`/api/rounds/${id}/debrief`, "POST", body);

export async function deleteRound(id: number): Promise<boolean> {
  try {
    const r = await fetch(`/api/rounds/${id}`, { method: "DELETE" });
    return r.ok;
  } catch {
    return false;
  }
}
