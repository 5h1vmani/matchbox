/* Matchbox — bring-your-own-key AI client. Real provider calls when the user
   has set a key (Settings), graceful fallbacks otherwise, so the front-end
   behaviour (calm streaming, working -> ready) is identical either way.
   Engineering can point the same interface at a server proxy if preferred. */
(function () {
  const MODELS = { anthropic: "claude-sonnet-4-20250514", openai: "gpt-4o" };

  function config() {
    const profile = window.__mbProfile || "maya";
    return {
      provider: localStorage.getItem("mb_provider") || "anthropic",
      key: (localStorage.getItem("mb_key_" + profile) || "").trim(),
      endpoint: (localStorage.getItem("mb_key_" + profile) || "").trim(),
      on: localStorage.getItem("mb_ai_on") !== "false",
    };
  }
  function hasKey() { return !!config().key; }

  const sleep = (ms) => new Promise((r) => setTimeout(r, ms));

  // Stream a canned string out token-by-token so demo mode feels live.
  async function localStream(text, onToken, signal) {
    const words = String(text).split(/(\s+)/);
    let acc = "";
    for (let i = 0; i < words.length; i++) {
      if (signal && signal.aborted) break;
      acc += words[i];
      onToken && onToken(acc);
      if (words[i].trim()) await sleep(14 + Math.random() * 26);
    }
    return acc;
  }

  async function readSSE(resp, pick, onToken, signal) {
    const reader = resp.body.getReader();
    const dec = new TextDecoder();
    let buf = "", acc = "";
    while (true) {
      if (signal && signal.aborted) { reader.cancel(); break; }
      const { done, value } = await reader.read();
      if (done) break;
      buf += dec.decode(value, { stream: true });
      const lines = buf.split("\n");
      buf = lines.pop();
      for (const line of lines) {
        const t = line.trim();
        if (!t.startsWith("data:")) continue;
        const data = t.slice(5).trim();
        if (data === "[DONE]") continue;
        try { const piece = pick(JSON.parse(data)); if (piece) { acc += piece; onToken && onToken(acc); } } catch (e) {}
      }
    }
    return acc;
  }

  async function streamAnthropic(key, system, prompt, onToken, signal) {
    const resp = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST", signal,
      headers: { "content-type": "application/json", "x-api-key": key, "anthropic-version": "2023-06-01", "anthropic-dangerous-direct-browser-access": "true" },
      body: JSON.stringify({ model: MODELS.anthropic, max_tokens: 1024, system, stream: true, messages: [{ role: "user", content: prompt }] }),
    });
    if (!resp.ok || !resp.body) throw new Error("anthropic " + resp.status);
    return readSSE(resp, (j) => (j.type === "content_block_delta" && j.delta && j.delta.text) || "", onToken, signal);
  }

  async function streamOpenAI(key, system, prompt, onToken, signal) {
    const resp = await fetch("https://api.openai.com/v1/chat/completions", {
      method: "POST", signal,
      headers: { "content-type": "application/json", authorization: "Bearer " + key },
      body: JSON.stringify({ model: MODELS.openai, stream: true, messages: [{ role: "system", content: system }, { role: "user", content: prompt }] }),
    });
    if (!resp.ok || !resp.body) throw new Error("openai " + resp.status);
    return readSSE(resp, (j) => (j.choices && j.choices[0] && j.choices[0].delta && j.choices[0].delta.content) || "", onToken, signal);
  }

  // Main entry. Returns { text, source }. Always resolves (falls back).
  async function stream({ system, prompt, fallback, onToken, signal }) {
    const cfg = config();
    if (cfg.on && cfg.key) {
      try {
        let text;
        if (cfg.provider === "openai") text = await streamOpenAI(cfg.key, system || "", prompt, onToken, signal);
        else if (cfg.provider === "anthropic") text = await streamAnthropic(cfg.key, system || "", prompt, onToken, signal);
        if (text && text.trim()) return { text, source: "byok", provider: cfg.provider };
      } catch (e) { /* fall through */ }
    }
    if (cfg.on && window.claude && typeof window.claude.complete === "function") {
      try {
        const full = await window.claude.complete(prompt, { system });
        if (full && full.trim()) { const t = await localStream(full, onToken, signal); return { text: t, source: "claude" }; }
      } catch (e) { /* fall through */ }
    }
    const t = await localStream(fallback || "…", onToken, signal);
    return { text: t, source: "demo" };
  }

  window.MBAI = { config, hasKey, stream };
})();
