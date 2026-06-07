/* Profile API client — the identity block at the top of every rendered CV
   (name, contact, headline, links). It is plain data: nothing is computed or
   inferred here, the screen just edits one row. Reads fall back to an empty
   profile; the POST takes a snake_case body (links as one-per-line or
   comma-separated text) and returns the same GET view-model so the screen can
   refresh from the response. */

export interface ProfileDetails {
  fullName: string;
  email: string;
  phone: string;
  location: string;
  headline: string;
  links: string[];
}

/** Snake_case write body the server expects. `links` is free text — one link
    per line or comma-separated — which the server splits and normalizes. */
export interface ProfileDetailsBody {
  full_name: string;
  email?: string;
  phone?: string;
  location?: string;
  headline?: string;
  links?: string;
}

const JSON_HEADERS = { "Content-Type": "application/json" };

const EMPTY: ProfileDetails = {
  fullName: "",
  email: "",
  phone: "",
  location: "",
  headline: "",
  links: [],
};

export async function getProfileDetails(): Promise<ProfileDetails> {
  try {
    const r = await fetch("/api/profile/details");
    return r.ok ? ((await r.json()) as ProfileDetails) : EMPTY;
  } catch {
    return EMPTY;
  }
}

export async function saveProfileDetails(body: ProfileDetailsBody): Promise<ProfileDetails> {
  try {
    const r = await fetch("/api/profile/details", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    });
    return r.ok ? ((await r.json()) as ProfileDetails) : EMPTY;
  } catch {
    return EMPTY;
  }
}
