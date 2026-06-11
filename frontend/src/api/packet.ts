/* Application-packet API client — the read-and-act surface for a single
   application. The server returns the exact packet view-model (the resume
   artifact, the semantic coverage, the keyword presence, and the cover draft),
   so the screen renders it unchanged. Every call is wrapped: reads fall back to
   a null packet so the UI can show an honest empty state, writes fall back to
   null/empty so a failure leaves the surface untouched. */

export interface PacketMustHave {
  text: string;
  band: string;
  covered: boolean;
  evidence_bullet_id: number | null;
  evidence_verified: boolean | null;
}

export interface PacketKeywordPresence {
  requirement: string;
  present: boolean;
  matched_term: string | null;
}

export interface PacketCoverage {
  semantic: {
    must_haves: PacketMustHave[];
    gaps: string[];
  };
  keyword_presence: PacketKeywordPresence[];
}

export interface PacketResume {
  cvUrl: string;
  changesUrl: string | null;
}

export interface PacketCover {
  text: string | null;
  coverUrl: string | null;
}

export interface Packet {
  applicationId: number;
  jobId: number;
  runId: string | null;
  company: string;
  title: string;
  stage: string;
  resume: PacketResume | null;
  coverage: PacketCoverage | null;
  cover: PacketCover;
}

const JSON_HEADERS = { "Content-Type": "application/json" };

/** The packet for one application, or null on a missing/failed read. */
export async function getPacket(appId: string): Promise<Packet | null> {
  try {
    const r = await fetch(`/api/applications/${appId}/packet`);
    return r.ok ? ((await r.json()) as Packet) : null;
  } catch {
    return null;
  }
}

/** Persist the cover body; the server re-renders cover.pdf and returns its URL. */
export async function saveCover(appId: string, text: string): Promise<{ coverUrl: string | null }> {
  try {
    const r = await fetch(`/api/applications/${appId}/cover`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ text }),
    });
    if (r.ok) return (await r.json()) as { coverUrl: string | null };
  } catch {
    /* fall through */
  }
  return { coverUrl: null };
}

/* Mark applied: the server moves the application to `applied` and stamps a
   +7d follow-up reminder. It returns the full Application; the screen only
   needs the new stage. Null on failure. */
export async function submitPacket(appId: string): Promise<{ stage: string } | null> {
  try {
    const r = await fetch(`/api/applications/${appId}/submit`, {
      method: "POST",
      headers: JSON_HEADERS,
    });
    if (r.ok) return (await r.json()) as { stage: string };
  } catch {
    /* fall through */
  }
  return null;
}
