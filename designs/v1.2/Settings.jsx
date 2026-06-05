/* Matchbox — Settings: bring your own key. The AI assistant runs on a key the
   user supplies; it lives on this device only. Local-first, no accounts. */
const { useState: useSetState } = React;

const PROVIDERS = [
  { id: "anthropic", name: "Anthropic (Claude)", hint: "Recommended. Paste a key from console.anthropic.com" },
  { id: "openai", name: "OpenAI", hint: "Paste a key from platform.openai.com" },
  { id: "local", name: "Local model", hint: "Point at a model running on this machine (Ollama, LM Studio)" },
];

function Settings({ profile, flash }) {
  const keyName = "mb_key_" + (profile ? profile.id : "default");
  const [provider, setProvider] = useSetState(() => localStorage.getItem("mb_provider") || "anthropic");
  const [key, setKey] = useSetState(() => localStorage.getItem(keyName) || "");
  const [show, setShow] = useSetState(false);
  const [aiOn, setAiOn] = useSetState(() => localStorage.getItem("mb_ai_on") !== "false");
  const connected = key.trim().length > 0;
  const prov = PROVIDERS.find((p) => p.id === provider) || PROVIDERS[0];

  const save = () => {
    localStorage.setItem("mb_provider", provider);
    localStorage.setItem(keyName, key.trim());
    localStorage.setItem("mb_ai_on", aiOn ? "true" : "false");
    flash(connected ? "Saved. The assistant can use your key now." : "Saved.");
  };

  return (
    <div>
      <div className="studio-head">
        <h1>Settings</h1>
        <p className="sub">Matchbox runs on this machine. The AI assistant uses a key you provide, and that key never leaves your device except to reach the provider you choose.</p>
      </div>

      <div style={{ maxWidth: 660 }}>
        {/* BYOK */}
        <div className="sectionlabel"><Icon name="key-round" size={15} /> AI assistant
          <span className="sp">
            <span className={window.cx("mbadge", connected ? "t-ok" : "t-warn")} style={{ textTransform: "none", letterSpacing: 0, fontWeight: 500 }}>
              <Icon name={connected ? "check" : "circle"} size={11} /> {connected ? "Key set" : "No key yet"}
            </span>
          </span>
        </div>

        <div className="card2 pad-card" style={{ marginBottom: 18 }}>
          <div style={{ fontSize: 12.5, color: "var(--muted-foreground)", marginBottom: 8 }}>Provider</div>
          <div className="chiplist" style={{ marginBottom: 18 }}>
            {PROVIDERS.map((p) => (
              <button key={p.id} className={window.cx("fchip", provider === p.id && "active")} onClick={() => setProvider(p.id)}
                style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-pill)", padding: "7px 13px", background: provider === p.id ? "var(--foreground)" : "var(--card)", color: provider === p.id ? "var(--background)" : "var(--foreground)", fontSize: 13, cursor: "pointer", whiteSpace: "nowrap" }}>
                {p.name}
              </button>
            ))}
          </div>

          <div style={{ fontSize: 12.5, color: "var(--muted-foreground)", marginBottom: 8 }}>{prov.id === "local" ? "Endpoint" : "API key"}</div>
          <div className="linkrow" style={{ marginBottom: 10 }}>
            <div className="field" style={{ display: "flex", alignItems: "center", gap: 9, border: "1px solid var(--border)", borderRadius: 9, padding: "9px 12px", background: "var(--card)", flex: 1 }}>
              <Icon name="lock" size={15} style={{ color: "var(--muted-foreground)" }} />
              <input type={show ? "text" : "password"} value={key} onChange={(e) => setKey(e.target.value)}
                placeholder={prov.id === "local" ? "http://localhost:11434" : "sk-…"}
                style={{ border: 0, outline: 0, flex: 1, fontFamily: "var(--font-mono)", fontSize: 13.5, background: "none", color: "var(--foreground)" }} />
              <button className="iconbtn" onClick={() => setShow((v) => !v)} title={show ? "Hide" : "Show"}><Icon name={show ? "eye-off" : "eye"} size={15} /></button>
            </div>
          </div>
          <div style={{ fontSize: 12.5, color: "var(--muted-foreground)", lineHeight: 1.5, marginBottom: 14 }}>{prov.hint}</div>

          <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
            <button className="btn accent" onClick={save}><Icon name="check" size={15} /> Save key</button>
            <button className="btn outline" onClick={async () => {
              flash("Testing…");
              const res = await window.MBAI.stream({ system: "Reply with exactly: ok", prompt: "Reply with exactly: ok", fallback: "ok" });
              flash(res.source === "byok" ? "Connected. Your " + provider + " key works." : res.source === "claude" ? "Connected via Claude." : connected ? "Could not reach " + provider + " from here (likely CORS in preview). Your key is saved; the live call will work behind your backend." : "Add a key first.");
            }}><Icon name="plug" size={15} /> Test connection</button>
            {connected && <button className="btn ghost small" onClick={() => { setKey(""); localStorage.removeItem(keyName); flash("Key removed"); }} style={{ marginLeft: "auto", color: "var(--danger)" }}>Remove key</button>}
          </div>
        </div>

        {/* AI features toggle */}
        <div className="card2 pad-card" style={{ marginBottom: 18, display: "flex", alignItems: "center", gap: 14 }}>
          <span style={{ width: 34, height: 34, borderRadius: 8, background: "var(--oat-100)", color: "var(--oat-600)", display: "flex", alignItems: "center", justifyContent: "center", flex: "0 0 auto" }}><Icon name="sparkles" size={17} /></span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 600 }}>Use AI features</div>
            <div style={{ fontSize: 12.5, color: "var(--muted-foreground)", marginTop: 1 }}>Tailoring, prep briefs, and drafts. Turn off to use Matchbox as a plain tracker.</div>
          </div>
          <button className={window.cx("switch", aiOn && "on")} onClick={() => { setAiOn((v) => !v); }} aria-label="Toggle AI features" />
        </div>

        {/* privacy */}
        <div className="card2 pad-card" style={{ display: "flex", gap: 11, alignItems: "flex-start" }}>
          <Icon name="shield" size={16} style={{ color: "var(--success)", flex: "0 0 auto", marginTop: 1 }} />
          <div style={{ fontSize: 13, color: "var(--secondary-foreground)", lineHeight: 1.55 }}>
            Your CVs, notes, and applications stay in a local file on this machine. The only thing that ever leaves is the specific request you send to your chosen AI provider, using your own key. Switch people anytime from the menu in the corner; each person has their own file and their own key.
          </div>
        </div>
      </div>
    </div>
  );
}

window.Settings = Settings;
