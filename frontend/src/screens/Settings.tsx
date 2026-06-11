/* Matchbox — Settings (bring-your-own-key AI). The app holds no LLM client: the
   key lives in a 0600 file on this device and a localhost proxy calls the
   provider directly. Honest copy throughout; no dead "local" affordance (only the
   two providers the proxy actually supports). */
import { useEffect, useState } from "react";
import * as ai from "../api/ai";
import { cx } from "../lib/derive";
import { Icon } from "../ui/icon";

const PROVIDERS: { id: string; label: string }[] = [
  { id: "anthropic", label: "Anthropic (Claude)" },
  { id: "openai", label: "OpenAI" },
];

export function Settings({ flash }: { flash: (msg: string) => void }) {
  const [cfg, setCfg] = useState<ai.AIConfig | null>(null);
  const [model, setModel] = useState("");
  const [keyInput, setKeyInput] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void ai.getAIConfig().then((c) => {
      setCfg(c);
      setModel(c.model);
    });
  }, []);

  if (!cfg) return <div className="sub" style={{ padding: 20 }}>Loading…</div>;

  const patch = async (p: Partial<Pick<ai.AIConfig, "provider" | "model" | "on">>) => {
    const c = await ai.setAIConfig(p);
    setCfg(c);
    setModel(c.model);
  };

  const saveKey = async () => {
    if (!keyInput.trim()) return;
    setBusy(true);
    const c = await ai.setAIKey(keyInput.trim());
    setBusy(false);
    setCfg(c);
    setKeyInput("");
    flash("Key saved on this device.");
  };

  const removeKey = async () => {
    setBusy(true);
    const c = await ai.clearAIKey();
    setBusy(false);
    setCfg(c);
    flash("Key removed.");
  };

  return (
    <div>
      <div className="phead">
        <div>
          <h1>Settings</h1>
          <p className="sub">Optional live AI, on your own key. Everything heavy still runs through the manual handoff.</p>
        </div>
      </div>

      <section className="card" style={{ padding: "18px 20px", maxWidth: 660, marginBottom: 18 }}>
        <div className="sec-h" style={{ marginBottom: 14 }}>
          <span className="t">AI assistance</span>
          <span className={cx("badge", cfg.hasKey ? "ok" : "muted")} style={{ marginLeft: "auto" }}>
            {cfg.hasKey ? "Live (your key)" : "Demo (add a key)"}
          </span>
        </div>

        <p className="sub" style={{ marginBottom: 16 }}>
          Your key, your provider. The key is stored only on this device (a <code>0600</code> file
          beside your data, never in the browser) and a localhost proxy uses it to call your provider
          directly. We store nothing on our side. Parsing and prose are real model calls, stated
          plainly. Without a key, the assistant streams a clearly-labelled demo and the real,
          grounded drafts still come from the manual handoff in Claude Code.
        </p>

        <label className="fld">
          <span className="fld__l">Provider</span>
          <div style={{ display: "flex", gap: 8 }}>
            {PROVIDERS.map((p) => (
              <button
                key={p.id}
                className={cx("btn", cfg.provider === p.id ? "primary" : "ghost")}
                onClick={() => void patch({ provider: p.id })}
              >
                {p.label}
              </button>
            ))}
          </div>
        </label>

        <label className="fld" style={{ marginTop: 14 }}>
          <span className="fld__l">Model</span>
          <div style={{ display: "flex", gap: 8 }}>
            <input
              className="inp"
              value={model}
              onChange={(e) => setModel(e.target.value)}
              placeholder="model id"
              style={{ flex: 1 }}
            />
            <button className="btn ghost" disabled={model === cfg.model} onClick={() => void patch({ model })}>
              Save
            </button>
          </div>
        </label>

        <label className="fld" style={{ marginTop: 14 }}>
          <span className="fld__l">Provider key</span>
          {cfg.hasKey ? (
            <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
              <span className="sub" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
                <Icon name="check-circle" size={15} /> A key is set on this device.
              </span>
              <button className="btn ghost" disabled={busy} onClick={() => void removeKey()} style={{ marginLeft: "auto" }}>
                Remove
              </button>
            </div>
          ) : (
            <div style={{ display: "flex", gap: 8 }}>
              <input
                className="inp"
                type="password"
                value={keyInput}
                onChange={(e) => setKeyInput(e.target.value)}
                placeholder={cfg.provider === "openai" ? "sk-…" : "sk-ant-…"}
                style={{ flex: 1 }}
                autoComplete="off"
              />
              <button className="btn primary" disabled={busy || !keyInput.trim()} onClick={() => void saveKey()}>
                Save key
              </button>
            </div>
          )}
        </label>

        <label className="fld" style={{ marginTop: 16, flexDirection: "row", alignItems: "center", gap: 10 }}>
          <input type="checkbox" checked={cfg.on} onChange={() => void patch({ on: !cfg.on })} />
          <span className="fld__l" style={{ margin: 0 }}>Enable live generation when a key is set</span>
        </label>
      </section>
    </div>
  );
}
