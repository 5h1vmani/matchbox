/* Sources API client — the job-board connectors. A "source" is one ATS board
   (Greenhouse, Lever, Ashby…) the user points at a company, plus the no-auth
   aggregators and an optional bring-your-own-key Adzuna feed. Scans are real,
   live network fetches: a bad slug shows up honestly as a `last_error` after a
   scan rather than being hidden. Every call try/catches with a safe fallback so
   the screen always renders. Writes that can fail in known ways (400 unsupported
   type, 409 duplicate) come back as a tagged result so the screen can flash a
   calm, specific message. */

export interface Source {
  id: number;
  ats_type: string;
  slug: string;
  company: string;
  country: string | null;
  sector: string | null;
  enabled: number;
  job_count: number;
  last_ok_at: string | null;
  last_error: string | null;
  last_attempt_at: string | null;
}

export interface SourcesView {
  sources: Source[];
  atsTypes: string[];
  adzuna: Record<string, unknown>;
}

export interface AddSourceBody {
  ats_type: string;
  slug: string;
  company: string;
  country?: string | null;
  sector?: string | null;
}

/** Outcome of an add: either the created source, or a known rejection. `error`
    is "duplicate" (409), "bad_type" (400), or "failed" (anything else). */
export type AddSourceResult =
  | { ok: true; source: Source }
  | { ok: false; error: "duplicate" | "bad_type" | "failed" };

/** Result of a single live scan: the refreshed source row plus whatever the
    backend reported about the fetch (inserted/fetched counts, etc.). */
export interface ScanResult {
  source: Source;
  result: Record<string, unknown>;
}

/** One aggregator's line in a remote scan. */
export interface RemoteResult {
  name: string;
  ok: boolean;
  inserted: number;
  fetched: number;
  error: string | null;
}

export interface AdzunaBody {
  app_id: string;
  app_key: string;
  country?: string | null;
  what?: string | null;
}

const JSON_HEADERS = { "Content-Type": "application/json" };

const EMPTY_VIEW: SourcesView = { sources: [], atsTypes: [], adzuna: {} };

export async function getSources(): Promise<SourcesView> {
  try {
    const r = await fetch("/api/sources");
    return r.ok ? ((await r.json()) as SourcesView) : EMPTY_VIEW;
  } catch {
    return EMPTY_VIEW;
  }
}

export async function addSource(body: AddSourceBody): Promise<AddSourceResult> {
  try {
    const r = await fetch("/api/sources", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    });
    if (r.status === 409) return { ok: false, error: "duplicate" };
    if (r.status === 400) return { ok: false, error: "bad_type" };
    if (!r.ok) return { ok: false, error: "failed" };
    return { ok: true, source: (await r.json()) as Source };
  } catch {
    return { ok: false, error: "failed" };
  }
}

export async function deleteSource(id: number): Promise<boolean> {
  try {
    const r = await fetch(`/api/sources/${id}`, { method: "DELETE" });
    return r.ok;
  } catch {
    return false;
  }
}

export async function toggleSource(id: number): Promise<Source | null> {
  try {
    const r = await fetch(`/api/sources/${id}/toggle`, {
      method: "POST",
      headers: JSON_HEADERS,
    });
    return r.ok ? ((await r.json()) as Source) : null;
  } catch {
    return null;
  }
}

export async function scanSource(id: number): Promise<ScanResult | null> {
  try {
    const r = await fetch(`/api/sources/${id}/scan`, {
      method: "POST",
      headers: JSON_HEADERS,
    });
    return r.ok ? ((await r.json()) as ScanResult) : null;
  } catch {
    return null;
  }
}

export async function scanRemote(): Promise<RemoteResult[]> {
  try {
    const r = await fetch("/api/sources/scan-remote", {
      method: "POST",
      headers: JSON_HEADERS,
    });
    if (!r.ok) return [];
    const data = (await r.json()) as { results?: RemoteResult[] };
    return data.results ?? [];
  } catch {
    return [];
  }
}

export async function saveAdzuna(body: AdzunaBody): Promise<boolean> {
  try {
    const r = await fetch("/api/sources/adzuna", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    });
    return r.ok;
  } catch {
    return false;
  }
}
