/* Discovery API client — the only place that talks to /api/discovery/*.
   Adapts nothing: the server returns the exact `Role` / `WatchedCompany`
   view-model (discovery_api/repo.py serializes DB -> view-model), so the ported
   components stay unchanged. Decisions return the updated role(s) plus, for
   `tailoring`, the manual run hand-off (run id + prompt). */
import type { DecisionInput, Role, WatchedCompany } from "../types";

const JSON_HEADERS = { "Content-Type": "application/json" };

async function getJSON<T>(url: string, fallback: T): Promise<T> {
  try {
    const r = await fetch(url);
    return r.ok ? ((await r.json()) as T) : fallback;
  } catch {
    return fallback;
  }
}

/** A decision's persisted result: the affected roles + optional run hand-off. */
export interface DecisionResult {
  roles: Role[];
  run?: { runId: string; prompt: string } | null;
}

async function postJSON(url: string, body: unknown): Promise<DecisionResult> {
  try {
    const r = await fetch(url, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body) });
    if (!r.ok) return { roles: [] };
    return (await r.json()) as DecisionResult;
  } catch {
    return { roles: [] };
  }
}

/** The full scored-role set (queue order is applied client-side, as in the design). */
export const listRoles = () => getJSON<Role[]>("/api/discovery/roles", []);
/** One role with its full JD (the list trims it; the drawer fetches it on open). */
export const getRole = (id: string) => getJSON<Role | null>(`/api/discovery/roles/${id}`, null);
export const listWatch = () => getJSON<WatchedCompany[]>("/api/discovery/watchlist", []);

/** Stop watching a company; resolves to the updated watchlist, or null on failure. */
async function postWatchlist(url: string, body: unknown): Promise<WatchedCompany[] | null> {
  try {
    const r = await fetch(url, { method: "POST", headers: JSON_HEADERS, body: JSON.stringify(body) });
    return r.ok ? ((await r.json()) as WatchedCompany[]) : null;
  } catch {
    return null;
  }
}
export const unwatch = (company: string) => postWatchlist("/api/discovery/unwatch", { company });

export const decide = (id: string, decision: DecisionInput) =>
  postJSON("/api/discovery/decide", { id, decision });

export const batchDecide = (ids: string[], decision: DecisionInput) =>
  postJSON("/api/discovery/batch", { ids, decision });
