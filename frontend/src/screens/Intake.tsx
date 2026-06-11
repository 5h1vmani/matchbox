/* Matchbox — first-run intake. The honest front door: you drop in an old CV, a
   LinkedIn export, or plain notes, and they stay on this machine. Nothing is
   read until you run the ingest, and nothing counts until you confirm every
   extracted fact at Review. No on-device magic is implied — a model reads the
   files when you ask it to, and you stay in the loop. The screen only stages
   files; the ingest itself is the `ingest my files` command you paste into
   Claude Code. While files are staged it polls the counts endpoint so the
   ingest's progress shows up here, and the next step after verification is
   pasting one job ad by hand — ATS scanners are optional automation, later. */
import { useEffect, useState } from "react";
import * as tapi from "../api/client";
import * as api from "../api/onboarding";
import * as rapi from "../api/review";
import { cx } from "../lib/derive";
import { Icon } from "../ui/icon";

const INGEST_CMD = "ingest my files";
const ACCEPT = ".pdf,.docx,.doc,.txt,.md,.json,.html,.rtf";
const POLL_MS = 5000;

function humanSize(bytes: number): string {
  if (bytes < 1024) return bytes + " B";
  if (bytes < 1024 * 1024) return (bytes / 1024).toFixed(bytes < 10 * 1024 ? 1 : 0) + " KB";
  return (bytes / (1024 * 1024)).toFixed(1) + " MB";
}

export function Intake({ flash, onGoSources }: { flash: (msg: string) => void; onGoSources?: () => void }) {
  const [staged, setStaged] = useState<api.StagedFile[]>([]);
  const [busy, setBusy] = useState(false);
  const [dragging, setDragging] = useState(false);
  const [notes, setNotes] = useState("");
  const [copied, setCopied] = useState(false);
  const [slug, setSlug] = useState("");
  const [creating, setCreating] = useState(false);
  const [newName, setNewName] = useState("");
  const [counts, setCounts] = useState<rapi.ReviewCounts | null>(null);

  useEffect(() => {
    void api.getOnboarding().then((o) => setStaged(o.staged));
    void tapi.getProfile().then((p) => setSlug(p.slug));
  }, []);

  // While files are staged the user is presumably running `ingest my files`
  // in Claude Code; poll the cheap counts endpoint so the ingest's progress
  // is visible here, not just in the terminal. The poll pauses while the tab
  // is hidden (visibilitychange) to stay cheap.
  useEffect(() => {
    if (staged.length === 0) return;
    let interval: ReturnType<typeof setInterval> | null = null;
    const tick = () => void rapi.getCounts().then(setCounts);
    const start = () => {
      if (interval === null) {
        tick();
        interval = setInterval(tick, POLL_MS);
      }
    };
    const stop = () => {
      if (interval !== null) {
        clearInterval(interval);
        interval = null;
      }
    };
    const onVisibility = () => (document.hidden ? stop() : start());
    document.addEventListener("visibilitychange", onVisibility);
    if (!document.hidden) start();
    return () => {
      stop();
      document.removeEventListener("visibilitychange", onVisibility);
    };
  }, [staged.length]);

  const createProfile = async () => {
    const trimmed = newName.trim();
    if (!trimmed || busy) return;
    setBusy(true);
    const made = await tapi.createUser(trimmed);
    setBusy(false);
    if (made) window.location.reload();
    else flash("Could not create that profile. Try a different name.");
  };

  const upload = async (files: File[]) => {
    if (files.length === 0 || busy) return;
    setBusy(true);
    const result = await api.uploadFiles(files);
    setBusy(false);
    if (result.rejected) {
      flash("That file type is not supported. Try a PDF, DOCX, TXT, MD, JSON, HTML, or RTF.");
      return;
    }
    if (result.staged.length > 0) {
      setStaged(result.staged);
      flash(result.staged.length === 1 ? "Staged 1 file." : `Staged ${result.staged.length} files.`);
    }
  };

  const onPick = (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files ? Array.from(e.target.files) : [];
    void upload(files);
    e.target.value = "";
  };

  const onDrop = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    setDragging(false);
    const files = e.dataTransfer.files ? Array.from(e.dataTransfer.files) : [];
    void upload(files);
  };

  const onDragOver = (e: React.DragEvent<HTMLDivElement>) => {
    e.preventDefault();
    if (!dragging) setDragging(true);
  };

  const paste = async () => {
    const text = notes.trim();
    if (!text || busy) return;
    setBusy(true);
    const result = await api.pasteNotes(text);
    setBusy(false);
    if (result.rejected) {
      flash("Those notes could not be saved.");
      return;
    }
    if (result.staged.length > 0) {
      setStaged(result.staged);
      setNotes("");
      flash("Notes staged.");
    }
  };

  const remove = async (name: string) => {
    if (busy) return;
    setBusy(true);
    const ok = await api.removeStaged(name);
    setBusy(false);
    if (ok) {
      setStaged((rows) => rows.filter((f) => f.name !== name));
      flash("Removed.");
    }
  };

  const copyCmd = () => {
    void navigator.clipboard?.writeText(INGEST_CMD);
    setCopied(true);
    setTimeout(() => setCopied(false), 1600);
    flash("Copied. Paste it into Claude Code.");
  };

  return (
    <div>
      <div className="phead">
        <div>
          <h1>Onboarding</h1>
          <p className="sub">
            Your files stay on this machine. When you run the ingest, a model reads them to pull out
            your experience. You review every extracted fact before it counts. Nothing is used until
            you confirm it.
          </p>
        </div>
      </div>

      {slug === "demo" && (
        <section
          className="card"
          style={{ padding: "12px 20px", marginBottom: 18, display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}
        >
          <Icon name="info" size={15} style={{ color: "var(--muted-foreground)", flex: "0 0 auto" }} />
          <span className="sub" style={{ flex: 1, minWidth: 220, margin: 0 }}>
            You are viewing the sample profile — create your own to begin
          </span>
          {creating ? (
            <form
              onSubmit={(e) => { e.preventDefault(); void createProfile(); }}
              style={{ display: "flex", gap: 8, alignItems: "center" }}
            >
              <input
                className="inp"
                autoFocus
                value={newName}
                placeholder="Your name"
                aria-label="Your name"
                onChange={(e) => setNewName(e.target.value)}
              />
              <button className="btn tiny" type="submit" disabled={busy || !newName.trim()}>
                Create
              </button>
            </form>
          ) : (
            <button className="btn tiny" onClick={() => setCreating(true)}>
              <Icon name="user-plus" size={13} /> Create my profile
            </button>
          )}
        </section>
      )}

      <section className="card" style={{ padding: "16px 20px", marginBottom: 18 }}>
        <div className="sec-h" style={{ marginBottom: 14 }}>
          <span className="t">Add your files</span>
        </div>

        <div
          className={cx("card", dragging && "drag")}
          style={{
            padding: "28px 20px",
            textAlign: "center",
            border: "1px dashed var(--border)",
            background: dragging ? "var(--muted)" : "transparent",
          }}
          onDragOver={onDragOver}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
        >
          <span
            className="ic"
            style={{
              width: 36,
              height: 36,
              borderRadius: 9,
              background: "var(--muted)",
              color: "var(--muted-foreground)",
              display: "inline-flex",
              alignItems: "center",
              justifyContent: "center",
              marginBottom: 10,
            }}
          >
            <Icon name="upload" size={18} />
          </span>
          <p className="sub" style={{ margin: "0 0 12px" }}>
            Drop in a CV, a LinkedIn export, or notes. PDF, DOCX, TXT, MD, JSON, HTML, or RTF.
          </p>
          <label className="btn" style={{ cursor: "pointer" }}>
            <Icon name="upload" size={14} /> Choose files
            <input type="file" multiple accept={ACCEPT} onChange={onPick} style={{ display: "none" }} />
          </label>
        </div>

        <div className="fld" style={{ marginTop: 16 }}>
          <span className="fld__l">Or paste notes</span>
          <textarea
            className="inp"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Paste anything that describes your work: roles, projects, bullet points…"
            rows={4}
            style={{ resize: "vertical", fontFamily: "inherit" }}
          />
          <div style={{ marginTop: 8 }}>
            <button className="btn tiny" disabled={busy || !notes.trim()} onClick={() => void paste()}>
              <Icon name="file-text" size={13} /> Stage notes
            </button>
          </div>
        </div>
      </section>

      <section className="card" style={{ padding: "16px 20px", marginBottom: 18 }}>
        <div className="sec-h" style={{ marginBottom: 12 }}>
          <span className="t">Staged</span>
          {staged.length > 0 && <span className="badge muted" style={{ marginLeft: "auto" }}>{staged.length}</span>}
        </div>

        {staged.length === 0 ? (
          <p className="sub" style={{ margin: 0 }}>Nothing staged yet. Drop in a CV, a LinkedIn export, or notes.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
            {staged.map((f) => (
              <div
                key={f.name}
                style={{ display: "flex", alignItems: "center", gap: 10, padding: "8px 0", borderBottom: "1px solid var(--border)" }}
              >
                <Icon name="file-text" size={15} style={{ color: "var(--muted-foreground)", flex: "0 0 auto" }} />
                <span style={{ flex: 1, minWidth: 0, overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{f.name}</span>
                <span className="sub mono" style={{ flex: "0 0 auto" }}>{humanSize(f.size)}</span>
                <button
                  className="btn ghost tiny"
                  disabled={busy}
                  title="Remove"
                  aria-label={`Remove ${f.name}`}
                  onClick={() => void remove(f.name)}
                  style={{ flex: "0 0 auto" }}
                >
                  <Icon name="x" size={13} />
                </button>
              </div>
            ))}
          </div>
        )}
      </section>

      <section className="card" style={{ padding: "16px 20px" }}>
        <div className="sec-h" style={{ marginBottom: 12 }}>
          <span className="t">Run the ingest</span>
        </div>
        <p className="sub" style={{ margin: "0 0 12px" }}>
          When your files are staged, paste this into Claude Code. It reads what you staged and pulls
          out your experience.
        </p>
        <div className="handoff__cmd" style={{ display: "flex", alignItems: "center", gap: 10 }}>
          <code style={{ flex: 1 }}>{INGEST_CMD}</code>
          <button className="btn tiny" onClick={copyCmd} style={{ flex: "0 0 auto" }}>
            <Icon name={copied ? "check" : "copy"} size={13} /> {copied ? "Copied" : "Copy"}
          </button>
        </div>
        {staged.length > 0 && counts !== null && (
          <p className="sub" style={{ margin: "12px 0 0", display: "flex", alignItems: "center", gap: 7 }}>
            <span className="live" />
            {counts.bullets > 0 ? (
              <span>
                <span className="mono">{counts.bullets}</span> bullet{counts.bullets === 1 ? "" : "s"} landed,{" "}
                <span className="mono">{counts.verified}</span> verified.
              </span>
            ) : (
              <span>Watching for the ingest. Nothing has landed yet.</span>
            )}
          </p>
        )}
        {staged.length > 0 && (
          <p className="sub" style={{ margin: "12px 0 0" }}>
            Once you have ingested, head to Review to confirm the facts.
          </p>
        )}
      </section>

      <section className="card" style={{ padding: "16px 20px", marginTop: 18 }}>
        <div className="sec-h" style={{ marginBottom: 12 }}>
          <span className="t">Then: your first job</span>
        </div>
        <p className="sub" style={{ margin: "0 0 12px" }}>
          Once your facts are verified, paste one job ad and tailor a CV against it. There is nothing
          to configure first; setting up ATS scanners is optional and can wait.
        </p>
        <div style={{ display: "flex", gap: 10, alignItems: "center", flexWrap: "wrap" }}>
          <button className="btn primary" onClick={onGoSources}>
            <Icon name="plus" size={14} /> Paste a job ad
          </button>
          <button className="btn ghost" onClick={onGoSources}>
            <Icon name="rss" size={14} /> Automate your scan (optional, later)
          </button>
        </div>
      </section>
    </div>
  );
}
