/* Onboarding API client — the first-run intake. Files the user drops (an old CV,
   a LinkedIn export, plain notes) are staged on this machine, never uploaded
   anywhere else; the ingest step is what a model reads to pull out experience.
   The server returns the exact `StagedFile` view-model, so the screen renders it
   unchanged. Reads fall back to an empty intake; a rejected file type comes back
   as 415 so the screen can flash a calm, honest error instead of a list. */

export interface StagedFile {
  name: string;
  size: number;
  rel_path: string;
}

export interface Onboarding {
  staged: StagedFile[];
  hasProfile: boolean;
}

/** Result of an upload/paste: the refreshed staged list, plus whether the server
    rejected a file type (415) so the screen can speak to it plainly. */
export interface StageResult {
  staged: StagedFile[];
  rejected: boolean;
}

const EMPTY: Onboarding = { staged: [], hasProfile: false };

export async function getOnboarding(): Promise<Onboarding> {
  try {
    const r = await fetch("/api/onboarding");
    return r.ok ? ((await r.json()) as Onboarding) : EMPTY;
  } catch {
    return EMPTY;
  }
}

export async function uploadFiles(files: File[]): Promise<StageResult> {
  if (files.length === 0) return { staged: [], rejected: false };
  // Do NOT set Content-Type — the browser adds the multipart boundary itself.
  const form = new FormData();
  for (const file of files) form.append("files", file);
  try {
    const r = await fetch("/api/onboarding/upload", { method: "POST", body: form });
    if (r.status === 415) return { staged: [], rejected: true };
    const staged = r.ok ? ((await r.json()) as StagedFile[]) : [];
    return { staged, rejected: false };
  } catch {
    return { staged: [], rejected: false };
  }
}

export async function pasteNotes(text: string): Promise<StageResult> {
  const form = new FormData();
  form.append("text", text);
  try {
    const r = await fetch("/api/onboarding/paste", { method: "POST", body: form });
    if (r.status === 415) return { staged: [], rejected: true };
    const staged = r.ok ? ((await r.json()) as StagedFile[]) : [];
    return { staged, rejected: false };
  } catch {
    return { staged: [], rejected: false };
  }
}

export async function removeStaged(name: string): Promise<boolean> {
  try {
    const r = await fetch(`/api/onboarding/staged/${encodeURIComponent(name)}`, { method: "DELETE" });
    return r.ok;
  } catch {
    return false;
  }
}
