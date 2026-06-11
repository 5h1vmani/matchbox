/* API client — the only place that talks to the FastAPI backend.
   Adapts nothing: the server already returns the exact `Application` view-model
   (the repo serializes DB -> view-model), so components stay unchanged. */
import type { Application, ResponseType, StageId } from "../types";

const JSON_HEADERS = { "Content-Type": "application/json" };

async function getJSON<T>(url: string, fallback: T): Promise<T> {
  try {
    const r = await fetch(url);
    return r.ok ? ((await r.json()) as T) : fallback;
  } catch {
    return fallback;
  }
}

async function postJSON(url: string, body?: unknown): Promise<Application | null> {
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: JSON_HEADERS,
      body: body ? JSON.stringify(body) : undefined,
    });
    return r.ok ? ((await r.json()) as Application) : null;
  } catch {
    return null;
  }
}

export const listApplications = () => getJSON<Application[]>("/api/applications", []);

export const advance = (id: string) => postJSON(`/api/applications/${id}/advance`);
export const setStage = (id: string, stage: StageId) => postJSON(`/api/applications/${id}/stage`, { stage });
export const snooze = (id: string, days = 2) => postJSON(`/api/applications/${id}/snooze`, { days });
export const remind = (id: string, days: number) => postJSON(`/api/applications/${id}/remind`, { days });
export const markDone = (id: string) => postJSON(`/api/applications/${id}/done`);
export const logResponse = (id: string, type: ResponseType) => postJSON(`/api/applications/${id}/response`, { type });
export const addNote = (id: string, text: string) => postJSON(`/api/applications/${id}/note`, { text });
export const toggleStar = (id: string) => postJSON(`/api/applications/${id}/star`);

export interface ProfileInfo {
  name: string;
  initials: string;
  slug: string;
}
export interface UserInfo {
  slug: string;
  name: string;
  active: boolean;
}

export interface Artifact {
  id: number;
  applicationId: number;
  kind: string;
  path: string | null;
  body: string | null;
  status: string;
  createdAt: string;
}

export const listArtifacts = (appId: string | number, kind?: string) =>
  getJSON<Artifact[]>(
    `/api/applications/${appId}/artifacts${kind ? `?kind=${kind}` : ""}`,
    [],
  );

export async function markArtifactSent(appId: string | number, artifactId: number): Promise<void> {
  try {
    await fetch(`/api/applications/${appId}/artifacts/${artifactId}/status`, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ status: "sent" }),
    });
  } catch {
    /* fire-and-forget */
  }
}

export const getProfile = () => getJSON<ProfileInfo>("/api/profile", { name: "You", initials: "Y", slug: "" });
export const listUsers = () => getJSON<UserInfo[]>("/api/users", []);

export async function switchUser(slug: string): Promise<void> {
  try {
    await fetch("/api/users/switch", { method: "POST", headers: JSON_HEADERS, body: JSON.stringify({ slug }) });
  } catch {
    /* ignore; caller reloads */
  }
}
