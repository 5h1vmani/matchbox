/* BYOK AI client. Streams from the localhost proxy (/api/ai/stream) -- the
   provider key never touches the browser. With a key, prose streams live; without
   one the proxy returns 409 and we fall back to a canned demo stream, badged
   honestly via AISource. Also wraps the provider config, the write-only key, the
   verified-fact grounding, and the FORM-only voice check. */

export type AISource = "byok" | "demo";

export interface AIConfig {
  provider: string;
  model: string;
  on: boolean;
  hasKey: boolean;
}

export interface VoiceViolation {
  rule: string;
  detail: string;
}
export interface VoiceResult {
  ok: boolean;
  scope: string;
  violations: VoiceViolation[];
}

export interface FactBullet {
  id: number;
  text: string;
  has_metric: boolean;
}
export interface FactExperience {
  company: string;
  role: string;
  start_date: string | null;
  end_date: string | null;
  location: string | null;
  bullets: FactBullet[];
}
export interface Facts {
  verified_only: boolean;
  experiences: FactExperience[];
  projects: { id: number; name: string; text: string; url: string | null }[];
  skills: { name: string; category: string | null }[];
}

const JSON_HEADERS = { "Content-Type": "application/json" };
const DEFAULT_CONFIG: AIConfig = { provider: "anthropic", model: "", on: true, hasKey: false };

async function getJSON<T>(url: string, fallback: T): Promise<T> {
  try {
    const r = await fetch(url);
    return r.ok ? ((await r.json()) as T) : fallback;
  } catch {
    return fallback;
  }
}

export const getAIConfig = () => getJSON<AIConfig>("/api/ai/config", DEFAULT_CONFIG);
export const getFacts = (verified = true) =>
  getJSON<Facts>(`/api/library/facts?verified=${verified ? 1 : 0}`, {
    verified_only: verified,
    experiences: [],
    projects: [],
    skills: [],
  });

async function postConfig(url: string, body: unknown): Promise<AIConfig> {
  try {
    const r = await fetch(url, {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    });
    if (r.ok) return (await r.json()) as AIConfig;
  } catch {
    /* fall through */
  }
  return getAIConfig();
}

export const setAIConfig = (patch: Partial<Pick<AIConfig, "provider" | "model" | "on">>) =>
  postConfig("/api/ai/config", patch);
export const setAIKey = (key: string) => postConfig("/api/ai/key", { key });

export async function clearAIKey(): Promise<AIConfig> {
  try {
    const r = await fetch("/api/ai/key", { method: "DELETE" });
    if (r.ok) return (await r.json()) as AIConfig;
  } catch {
    /* fall through */
  }
  return getAIConfig();
}

export async function voiceCheck(text: string, scope = "cover"): Promise<VoiceResult> {
  try {
    const r = await fetch("/api/voice-check", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ text, scope }),
    });
    if (r.ok) return (await r.json()) as VoiceResult;
  } catch {
    /* fall through */
  }
  return { ok: true, scope, violations: [] };
}

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

/** Token-by-token replay of a canned string so demo mode reads as live. */
async function localStream(
  text: string,
  onToken?: (acc: string) => void,
  signal?: AbortSignal,
): Promise<string> {
  const words = String(text).split(/(\s+)/);
  let acc = "";
  for (const w of words) {
    if (signal?.aborted) break;
    acc += w;
    onToken?.(acc);
    if (w.trim()) await sleep(14 + Math.random() * 26);
  }
  return acc;
}

/** Read our normalized `data: {"text": ...}` SSE, accumulating into onToken(acc). */
async function readSSE(
  resp: Response,
  onToken?: (acc: string) => void,
  signal?: AbortSignal,
): Promise<string> {
  const reader = resp.body!.getReader();
  const dec = new TextDecoder();
  let buf = "";
  let acc = "";
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
      if (data === "[DONE]") continue;
      try {
        const obj = JSON.parse(data) as { text?: string; error?: string };
        if (obj.error) throw new Error(obj.error);
        if (obj.text) {
          acc += obj.text;
          onToken?.(acc);
        }
      } catch (e) {
        if (e instanceof Error && e.message && !(e instanceof SyntaxError)) throw e;
      }
    }
  }
  return acc;
}

export interface StreamArgs {
  system?: string;
  prompt: string;
  fallback?: string;
  onToken?: (acc: string) => void;
  signal?: AbortSignal;
  maxTokens?: number;
}

/** Always resolves: live BYOK when a key is set, else the badged demo stream.
    The real grounded artifact still comes from the manual handoff either way. */
export async function stream({
  system,
  prompt,
  fallback,
  onToken,
  signal,
  maxTokens = 1024,
}: StreamArgs): Promise<{ text: string; source: AISource }> {
  try {
    const resp = await fetch("/api/ai/stream", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify({ system, prompt, max_tokens: maxTokens }),
      signal,
    });
    if (!resp.ok || !resp.body) throw new Error("no-stream"); // 409 = no key -> demo
    const text = await readSSE(resp, onToken, signal);
    if (text.trim()) return { text, source: "byok" };
    throw new Error("empty");
  } catch {
    const text = await localStream(fallback || "…", onToken, signal);
    return { text, source: "demo" };
  }
}
