/* In-app brain client. Streams an ingest or tailor run from the localhost brain
   endpoints, which drive the SAME deterministic core the documented Claude Code
   handoff uses, but with the user's own stored BYOK key -- so a first-time user
   never needs a second terminal. With no key the endpoints return 409 and the UI
   keeps its copy-paste handoff (Claude Code remains the supported fallback).

   The SSE framing matches /api/ai/stream, so the reader below mirrors ai.ts's
   readSSE: it pulls `data: {...}` frames, surfacing each {step, detail} progress
   line and the final {done, ...} or {error} event to onEvent. */

export interface BrainStep {
  step: string;
  detail: string;
}

/** A run-complete event. The runner's result fields ride along on `done`. */
export interface BrainDone {
  done: true;
  // ingest result
  bullets?: number;
  experiences?: number;
  // tailor result
  run_id?: string;
  cv_path?: string;
  gaps?: string[];
  keyword_misses?: string[];
  polish_applied?: number;
}

export interface BrainError {
  error: string;
}

export type BrainEvent = BrainStep | BrainDone | BrainError;

export function isDone(e: BrainEvent): e is BrainDone {
  return (e as BrainDone).done === true;
}
export function isError(e: BrainEvent): e is BrainError {
  return typeof (e as BrainError).error === "string";
}
export function isStep(e: BrainEvent): e is BrainStep {
  return typeof (e as BrainStep).step === "string";
}

const JSON_HEADERS = { "Content-Type": "application/json" };

/** Outcome of starting a run: ok=false with a status carries the gate reason so
    the caller can fall back (409 = no key -> Claude Code handoff) or warn. */
export interface BrainStart {
  ok: boolean;
  status: number;
}

/** POST to a brain endpoint and drain the SSE stream into onEvent. Resolves when
    the stream ends (after the final done/error frame). A non-2xx response (409
    no key, 400 no confirm, 429 busy) resolves immediately with ok=false so the
    caller can fall back without throwing. */
async function runBrain(
  url: string,
  body: unknown,
  onEvent: (e: BrainEvent) => void,
  signal?: AbortSignal,
): Promise<BrainStart> {
  let resp: Response;
  try {
    resp = await fetch(url, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
      signal,
    });
  } catch {
    return { ok: false, status: 0 };
  }
  if (!resp.ok || !resp.body) return { ok: false, status: resp.status };

  const reader = resp.body.getReader();
  const dec = new TextDecoder();
  let buf = "";
  for (;;) {
    if (signal?.aborted) {
      await reader.cancel();
      break;
    }
    const { done, value } = await reader.read();
    if (done) break;
    buf += dec.decode(value, { stream: true });
    const lines = buf.split("\n");
    buf = lines.pop() ?? "";
    for (const line of lines) {
      const t = line.trim();
      if (!t.startsWith("data:")) continue;
      const data = t.slice(5).trim();
      if (!data || data === "[DONE]") continue;
      try {
        onEvent(JSON.parse(data) as BrainEvent);
      } catch {
        /* skip a partial/garbled frame */
      }
    }
  }
  return { ok: true, status: resp.status };
}

/** Stream an in-app ingest of the staged inbox files. `confirm` is the cost
    gate: the UI confirms before calling because the run spends the user's own
    API credits. */
export function runBrainIngest(
  onEvent: (e: BrainEvent) => void,
  signal?: AbortSignal,
): Promise<BrainStart> {
  return runBrain("/api/brain/ingest", { confirm: true }, onEvent, signal);
}

/** Stream an in-app tailoring run for one job. */
export function runBrainTailor(
  jobId: number,
  onEvent: (e: BrainEvent) => void,
  signal?: AbortSignal,
): Promise<BrainStart> {
  return runBrain("/api/brain/tailor", { job_id: jobId, confirm: true }, onEvent, signal);
}
