/* Jobs API client — adding a role by hand. Some openings never appear on a
   polled ATS board (a LinkedIn post, a company careers page, a referral). This
   lets the user paste that JD in directly. The new role lands as "new" and is
   scored by the same rubric as everything else once `score-new` runs, at which
   point it shows up in Discover. Every call try/catches with a safe fallback so
   the screen always renders. Writes that can fail in known ways (400 missing
   fields, 409 duplicate url) come back with the HTTP status so the screen can
   flash a calm, specific message. */

export interface AddJobBody {
  company: string;
  title: string;
  url: string;
  jd_text: string;
  apply_url?: string | null;
  location?: string | null;
}

/** Outcome of an add-by-hand. `status` is the HTTP status (0 on a network
    failure) so the screen can tell 200 / 400 / 409 apart. `id` is present only
    on a successful insert. */
export interface AddJobResult {
  ok: boolean;
  status: number;
  id?: number;
}

const JSON_HEADERS = { "Content-Type": "application/json" };

export async function addJobByHand(body: AddJobBody): Promise<AddJobResult> {
  try {
    const r = await fetch("/api/jobs", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    });
    if (!r.ok) return { ok: false, status: r.status };
    const data = (await r.json()) as { id: number };
    return { ok: true, status: r.status, id: data.id };
  } catch {
    return { ok: false, status: 0 };
  }
}

export async function scoreNewJobs(): Promise<{ scored: number }> {
  try {
    const r = await fetch("/api/jobs/score-new", {
      method: "POST",
      headers: JSON_HEADERS,
    });
    if (!r.ok) return { scored: 0 };
    const data = (await r.json()) as { scored?: number };
    return { scored: data.scored ?? 0 };
  } catch {
    return { scored: 0 };
  }
}
