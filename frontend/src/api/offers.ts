/* Offers API client — talks to the FastAPI backend for the offer ledger and the
   honest own-pool salary benchmark. Negotiation here is status-tracking only:
   the counter-offer draft is written by the user in Claude Code (and voice-
   checked there), never generated in the browser. Every call try/catches with a
   safe fallback so the screen always renders. */

export type OfferStatus = "received" | "negotiating" | "accepted" | "declined";

export interface Offer {
  id: number;
  applicationId: number;
  base: number | null;
  bonus: number | null;
  totalComp: number | null;
  equity: string | null;
  currency: string | null;
  location: string | null;
  status: string;
  receivedAt: string | null;
  notes: string | null;
  createdAt: string;
}

export interface CreateOfferBody {
  applicationId: number;
  base?: number | null;
  bonus?: number | null;
  equity?: string | null;
  currency?: string | null;
  location?: string | null;
  receivedAt?: string | null;
  notes?: string | null;
}

/** Honest benchmark: percentile of `base` against the user's own offer pool.
    `basis` is a verbatim, human-readable description of what was compared; show
    it as-is. When confidence is "none"/sampleSize 0, there is no real percentile. */
export interface Benchmark {
  percentile: number | null;
  sampleSize: number;
  median: number | null;
  range: { low: number; high: number } | null;
  basis: string;
  currency: string | null;
  confidence: "none" | "low" | "medium";
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

async function postJSON<T>(url: string, body: unknown, fallback: T): Promise<T> {
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    });
    return r.ok ? ((await r.json()) as T) : fallback;
  } catch {
    return fallback;
  }
}

export const listOffers = (applicationId?: number) =>
  getJSON<Offer[]>(
    applicationId === undefined ? "/api/offers" : `/api/offers?applicationId=${applicationId}`,
    [],
  );

export const createOffer = (body: CreateOfferBody) =>
  postJSON<Offer | null>("/api/offers", body, null);

export const setOfferStatus = (id: number, status: OfferStatus) =>
  postJSON<Offer | null>(`/api/offers/${id}/status`, { status }, null);

export function getBenchmark(
  base: number,
  roleFamily?: string,
  currency?: string,
): Promise<Benchmark> {
  const params = new URLSearchParams({ base: String(base) });
  if (roleFamily) params.set("roleFamily", roleFamily);
  if (currency) params.set("currency", currency);
  return getJSON<Benchmark>(`/api/offers/benchmark?${params.toString()}`, {
    percentile: null,
    sampleSize: 0,
    median: null,
    range: null,
    basis: "No matching salary data in your own pool yet.",
    currency: currency ?? null,
    confidence: "none",
  });
}
