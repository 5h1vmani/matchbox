/* Answers API client — the Library answer bank. A reusable Q&A store the user
   builds up (or ingests) and reaches for across applications. The server returns
   the exact `Answer` view-model, so the screen renders it unchanged. Every call
   is wrapped: reads fall back to an empty list, writes fall back to null so the
   UI can leave the row untouched on failure. */

export interface Answer {
  id: number;
  question: string;
  answer: string;
  category: string | null;
  verified: boolean;
  usedCount: number;
  sourceFile: string | null;
  createdAt: string;
}

export interface AnswerCreate {
  question: string;
  answer: string;
  category?: string | null;
  verified?: boolean;
}

export interface AnswerPatch {
  question?: string;
  answer?: string;
  category?: string | null;
  verified?: boolean;
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

async function sendJSON(url: string, method: string, body?: unknown): Promise<Answer | null> {
  try {
    const r = await fetch(url, {
      method,
      headers: JSON_HEADERS,
      body: body ? JSON.stringify(body) : undefined,
    });
    return r.ok ? ((await r.json()) as Answer) : null;
  } catch {
    return null;
  }
}

export const listAnswers = (verified?: boolean) => {
  const q = verified === undefined ? "" : `?verified=${verified ? 1 : 0}`;
  return getJSON<Answer[]>(`/api/answers${q}`, []);
};

export const createAnswer = (body: AnswerCreate) => sendJSON("/api/answers", "POST", body);

export const updateAnswer = (id: number, body: AnswerPatch) =>
  sendJSON(`/api/answers/${id}`, "PATCH", body);

export const useAnswer = (id: number) => sendJSON(`/api/answers/${id}/use`, "POST");

export async function deleteAnswer(id: number): Promise<boolean> {
  try {
    const r = await fetch(`/api/answers/${id}`, { method: "DELETE" });
    return r.ok;
  } catch {
    return false;
  }
}
