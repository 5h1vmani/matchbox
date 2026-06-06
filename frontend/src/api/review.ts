/* Review API client — the v0.3 honesty guardrail. A model pulls facts out of the
   user's files; nothing counts until the user confirms it here. The server returns
   the exact view-models, so the screen renders them unchanged. Every call is
   wrapped: the read falls back to an empty review state, writes fall back to null
   so the UI can leave the row untouched on failure. */

export interface ReviewBullet {
  id: number;
  experienceId: number;
  text: string;
  hasMetric: boolean;
  verified: boolean;
  sourceFile: string | null;
}

export interface ReviewExperience {
  id: number;
  company: string;
  role: string;
  startDate: string | null;
  endDate: string | null;
  bullets: ReviewBullet[];
}

export interface ReviewProject {
  id: number;
  name: string;
  text: string;
  url: string | null;
  verified: boolean;
}

export interface ReviewAnswer {
  id: number;
  question: string;
  answer: string;
  category: string | null;
  verified: boolean;
  usedCount: number;
  sourceFile: string | null;
  createdAt: string;
}

export interface ReviewState {
  experiences: ReviewExperience[];
  projects: ReviewProject[];
  answers: ReviewAnswer[];
  unverifiedBullets: number;
  unverifiedProjects: number;
  unverifiedAnswers: number;
}

export interface BulletPatch {
  text?: string;
  has_metric?: boolean;
}

export interface VerifyExperienceResult {
  experienceId: number;
  bullets: ReviewBullet[];
}

const JSON_HEADERS = { "Content-Type": "application/json" };

const EMPTY_REVIEW: ReviewState = {
  experiences: [],
  projects: [],
  answers: [],
  unverifiedBullets: 0,
  unverifiedProjects: 0,
  unverifiedAnswers: 0,
};

async function getJSON<T>(url: string, fallback: T): Promise<T> {
  try {
    const r = await fetch(url);
    return r.ok ? ((await r.json()) as T) : fallback;
  } catch {
    return fallback;
  }
}

async function sendJSON<T>(url: string, method: string, fallback: T, body?: unknown): Promise<T> {
  try {
    const r = await fetch(url, {
      method,
      headers: JSON_HEADERS,
      body: body ? JSON.stringify(body) : undefined,
    });
    return r.ok ? ((await r.json()) as T) : fallback;
  } catch {
    return fallback;
  }
}

export const getReview = () => getJSON<ReviewState>("/api/review", EMPTY_REVIEW);

export const verifyBullet = (id: number) =>
  sendJSON<ReviewBullet | null>(`/api/review/bullets/${id}/verify`, "POST", null);

export const unverifyBullet = (id: number) =>
  sendJSON<ReviewBullet | null>(`/api/review/bullets/${id}/unverify`, "POST", null);

export const editBullet = (id: number, body: BulletPatch) =>
  sendJSON<ReviewBullet | null>(`/api/review/bullets/${id}`, "PATCH", null, body);

export async function deleteBullet(id: number): Promise<boolean> {
  try {
    const r = await fetch(`/api/review/bullets/${id}`, { method: "DELETE" });
    return r.ok;
  } catch {
    return false;
  }
}

export const verifyExperience = (id: number) =>
  sendJSON<VerifyExperienceResult | null>(`/api/review/experiences/${id}/verify-all`, "POST", null);

export const verifyAll = () =>
  sendJSON<ReviewState>("/api/review/verify-all", "POST", EMPTY_REVIEW);

export const verifyProject = (id: number) =>
  sendJSON<ReviewProject | null>(`/api/review/projects/${id}/verify`, "POST", null);

export const verifyAnswer = (id: number) =>
  sendJSON<ReviewAnswer | null>(`/api/review/answers/${id}/verify`, "POST", null);
