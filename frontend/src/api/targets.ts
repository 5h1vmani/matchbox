/* Targets API client — the search criteria that feed the eligibility filter in
   Discover: which role families and locations you want, your dream companies and
   hard exclusions, plus work authorization (citizenships, sponsorship need,
   clearance). It is plain data: nothing is computed here, the screen just edits
   one row. Reads fall back to an empty Targets; the POST takes the same shape and
   returns the same view-model so the screen can refresh from the response. */

export interface WorkAuth {
  citizenships: string[];
  needs_sponsorship: boolean;
  has_clearance: boolean;
}

export interface Targets {
  role_families: string[];
  dream_companies: string[];
  locations: string[];
  exclusions: string[];
  work_auth: WorkAuth;
}

const JSON_HEADERS = { "Content-Type": "application/json" };

const EMPTY: Targets = {
  role_families: [],
  dream_companies: [],
  locations: [],
  exclusions: [],
  work_auth: {
    citizenships: [],
    needs_sponsorship: false,
    has_clearance: false,
  },
};

export async function getTargets(): Promise<Targets> {
  try {
    const r = await fetch("/api/targets");
    return r.ok ? ((await r.json()) as Targets) : EMPTY;
  } catch {
    return EMPTY;
  }
}

export async function saveTargets(body: Targets): Promise<Targets> {
  try {
    const r = await fetch("/api/targets", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    });
    return r.ok ? ((await r.json()) as Targets) : EMPTY;
  } catch {
    return EMPTY;
  }
}
