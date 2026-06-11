/* Doctor API client — the matchbox-doctor environment checks as JSON. The
   handoff UI uses it to be honest about the machine it is running on (is the
   claude CLI actually on PATH?) instead of telling the user to paste into a
   tool that may not exist. The read falls back to an empty list so a failed
   fetch never blocks the handoff itself. */

export interface DoctorCheck {
  name: string;
  ok: boolean;
  required: boolean;
  detail: string;
}

export async function getDoctorChecks(): Promise<DoctorCheck[]> {
  try {
    const r = await fetch("/api/doctor");
    if (!r.ok) return [];
    const data = (await r.json()) as { checks?: DoctorCheck[] };
    return data.checks ?? [];
  } catch {
    return [];
  }
}
