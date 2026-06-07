/* Insights API client — momentum (real weekly pace) and rejection reasons
   (captured close-reason categories). Both are honest arithmetic on the backend;
   the UI only renders what was measured. */

export interface Momentum {
  weekStart: string;
  weekEnd: string;
  target: number;
  applied: number;
  interviews: number;
  followups: number;
  status: "rest" | "healthy" | "push";
}

async function getJSON<T>(url: string, fallback: T): Promise<T> {
  try {
    const r = await fetch(url);
    return r.ok ? ((await r.json()) as T) : fallback;
  } catch {
    return fallback;
  }
}

export const getMomentum = (target = 5) =>
  getJSON<Momentum>(`/api/insights/momentum?target=${target}`, {
    weekStart: "",
    weekEnd: "",
    target,
    applied: 0,
    interviews: 0,
    followups: 0,
    status: "push",
  });

export const getRejectionReasons = () =>
  getJSON<Record<string, number>>("/api/insights/rejection-reasons", {});
