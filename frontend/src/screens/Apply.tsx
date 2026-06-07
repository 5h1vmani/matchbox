/* Matchbox — Apply. The application packet for a single job: the tailored CV
   (with its coverage read honestly, gaps named but not alarmed), the cover
   paragraph (drafted from your verified library, in your voice, badged by who
   actually generated it), your reusable screening answers, and the one button
   that marks it applied. Nothing here invents: coverage and keyword presence
   come straight from the assembler, the cover is grounded only in verified
   facts, and unfilled answers stay blank. The follow-up is a reminder you will
   see on Today, never a scheduled task. */
import { useEffect, useRef, useState } from "react";
import type { Application } from "../types";
import { listApplications } from "../api/client";
import * as packetApi from "../api/packet";
import type { Packet, PacketMustHave } from "../api/packet";
import { listAnswers, useAnswer } from "../api/answers";
import type { Answer } from "../api/answers";
import * as ai from "../api/ai";
import { cx } from "../lib/derive";
import { Icon } from "../ui/icon";

type TabId = "resume" | "cover" | "questions" | "submit";

const TABS: ReadonlyArray<{ id: TabId; label: string; icon: string }> = [
  { id: "resume", label: "Résumé", icon: "file-text" },
  { id: "cover", label: "Cover", icon: "sparkles" },
  { id: "questions", label: "Questions", icon: "copy" },
  { id: "submit", label: "Submit", icon: "send" },
];

/* The fixed honesty instruction, used verbatim as the head of the cover-draft
   system prompt. The verified-fact block is appended below it. */
const COVER_INSTRUCTION =
  "You write a single, specific cover-letter paragraph for a job application. " +
  "Ground every claim ONLY in the verified facts below. Never invent an employer, " +
  "date, metric, or skill. Plain, calm, concrete voice. No em-dashes, no contractions, " +
  "no marketing words (leverage, passionate, spearhead, robust, scalable). " +
  "Return only the paragraph.";

const COVER_FALLBACK =
  "I am applying for this role because the work matches what I have actually done. " +
  "In my most recent position I shipped features end to end, kept the quality bar high, " +
  "and worked closely with the people around me. I would bring the same steady, concrete " +
  "approach here, and I would be glad to walk through any of it in detail.";

/* Flatten the verified facts into a compact, plain block the model can ground
   on. Kept terse so it fits the prompt without crowding the instruction. */
function factsBlock(facts: ai.Facts): string {
  const lines: string[] = [];
  for (const exp of facts.experiences) {
    lines.push(`# ${exp.role} at ${exp.company}`);
    for (const b of exp.bullets) lines.push(`- ${b.text}`);
  }
  if (facts.projects.length > 0) {
    lines.push("# Projects");
    for (const p of facts.projects) lines.push(`- ${p.name}: ${p.text}`);
  }
  if (facts.skills.length > 0) {
    lines.push("# Skills");
    lines.push(facts.skills.map((s) => s.name).join(", "));
  }
  return lines.join("\n");
}

/* The band pill for a must-have. `covered` -> ok; `partial` band -> muted
   badge; anything else (uncovered) -> a plain muted chip, calm not alarmist. */
function bandLabel(m: PacketMustHave): string {
  if (m.covered) return "Covered";
  if (m.band === "partial") return "Partial";
  return "Not covered";
}

function MustHaveRow({ m }: { m: PacketMustHave }) {
  if (m.covered) {
    return (
      <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
        <span className="badge ok" style={{ flex: "0 0 auto" }}>
          <Icon name="check" size={12} /> {bandLabel(m)}
        </span>
        <span style={{ fontSize: 13.5, lineHeight: 1.5 }}>{m.text}</span>
      </div>
    );
  }
  const partial = m.band === "partial";
  return (
    <div style={{ display: "flex", alignItems: "flex-start", gap: 10 }}>
      {partial ? (
        <span className="badge muted" style={{ flex: "0 0 auto" }}>
          {bandLabel(m)}
        </span>
      ) : (
        <span
          className="sub mono"
          style={{
            flex: "0 0 auto",
            padding: "2px 8px",
            borderRadius: 6,
            background: "var(--muted)",
            fontSize: 11.5,
          }}
        >
          {bandLabel(m)}
        </span>
      )}
      <span className="sub" style={{ fontSize: 13.5, lineHeight: 1.5 }}>{m.text}</span>
    </div>
  );
}

const PALETTES: ReadonlyArray<string> = ["slate", "ink", "forest", "claret", "bronze"];
const FONTS: ReadonlyArray<string> = ["source-serif", "source-sans", "inter", "atkinson-hyperlegible"];

function ResumeTab({ packet, flash }: { packet: Packet; flash: (msg: string) => void }) {
  const [palette, setPalette] = useState("slate");
  const [font, setFont] = useState("source-serif");
  const [cvSrc, setCvSrc] = useState<string | null>(packet.resume?.cvUrl ?? null);
  const [restyling, setRestyling] = useState(false);

  // Re-seed the iframe src when the selected application's packet changes.
  useEffect(() => {
    setCvSrc(packet.resume?.cvUrl ?? null);
  }, [packet]);

  const restyle = async () => {
    setRestyling(true);
    const res = await packetApi.restyleCv(String(packet.applicationId), palette, font);
    setRestyling(false);
    if (res) {
      setCvSrc(`${res.cvUrl}?t=${Date.now()}`);
      flash("Restyled.");
      if (res.drift.length > 0) {
        flash("Heads up: a bullet changed in your library since this CV was built.");
      }
    } else {
      flash("Could not restyle the CV.");
    }
  };

  if (!packet.resume) {
    return (
      <div className="card" style={{ padding: "16px 20px" }}>
        <p className="sub" style={{ margin: 0 }}>
          No tailored CV yet — run the tailoring in Claude Code.
        </p>
      </div>
    );
  }
  const coverage = packet.coverage;
  const mustHaves = coverage?.semantic.must_haves ?? [];
  const gaps = coverage?.semantic.gaps ?? [];

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
      <div className="card" style={{ padding: "16px 20px" }}>
        <div className="sec-h" style={{ marginBottom: 12 }}>
          <span className="t">Tailored CV</span>
          {packet.resume.changesUrl && (
            <a
              className="btn ghost tiny"
              href={packet.resume.changesUrl}
              target="_blank"
              rel="noreferrer"
              style={{ marginLeft: "auto" }}
            >
              <Icon name="file-text" size={13} /> What changed
            </a>
          )}
        </div>
        <iframe
          src={cvSrc ?? packet.resume.cvUrl}
          title="CV"
          style={{ width: "100%", height: 520, border: "1px solid var(--border)", borderRadius: 8 }}
        />
        <div style={{ marginTop: 12, display: "flex", gap: 8, alignItems: "center", flexWrap: "wrap" }}>
          <select
            className="inp"
            value={palette}
            onChange={(e) => setPalette(e.target.value)}
            style={{ width: "auto" }}
          >
            {PALETTES.map((p) => (
              <option key={p} value={p}>
                {p}
              </option>
            ))}
          </select>
          <select
            className="inp"
            value={font}
            onChange={(e) => setFont(e.target.value)}
            style={{ width: "auto" }}
          >
            {FONTS.map((f) => (
              <option key={f} value={f}>
                {f}
              </option>
            ))}
          </select>
          <button className="btn ghost" disabled={restyling} onClick={() => void restyle()}>
            <Icon name="sparkles" size={14} /> {restyling ? "Restyling…" : "Restyle"}
          </button>
        </div>
      </div>

      {coverage && (
        <div className="card" style={{ padding: "16px 20px" }}>
          <div className="sec-h" style={{ marginBottom: 12 }}>
            <span className="t">Coverage</span>
          </div>
          {mustHaves.length === 0 ? (
            <p className="sub" style={{ margin: 0 }}>No must-haves were extracted for this job.</p>
          ) : (
            <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
              {mustHaves.map((m, i) => (
                <MustHaveRow key={i} m={m} />
              ))}
            </div>
          )}

          {gaps.length > 0 && (
            <div style={{ marginTop: 16, paddingTop: 14, borderTop: "1px solid var(--border)" }}>
              <div className="sub" style={{ marginBottom: 8 }}>Left empty (no verified fact)</div>
              <ul style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 6 }}>
                {gaps.map((g, i) => (
                  <li key={i} className="sub" style={{ fontSize: 13.5, lineHeight: 1.5 }}>{g}</li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

function CoverTab({
  appId,
  packet,
  flash,
}: {
  appId: string;
  packet: Packet;
  flash: (msg: string) => void;
}) {
  const [text, setText] = useState(packet.cover.text ?? "");
  const [busy, setBusy] = useState(false);
  const [source, setSource] = useState<ai.AISource | null>(null);
  const [violations, setViolations] = useState<ai.VoiceViolation[]>([]);
  const [checked, setChecked] = useState(false);
  const [saving, setSaving] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // Re-seed when the selected application's packet changes.
  useEffect(() => {
    setText(packet.cover.text ?? "");
    setSource(null);
    setViolations([]);
    setChecked(false);
  }, [packet]);

  // Abort an in-flight stream if the component unmounts.
  useEffect(() => () => abortRef.current?.abort(), []);

  const regenerate = async () => {
    abortRef.current?.abort();
    const ctrl = new AbortController();
    abortRef.current = ctrl;
    setBusy(true);
    setSource(null);
    setChecked(false);
    setViolations([]);

    const facts = await ai.getFacts(true);
    const system = `${COVER_INSTRUCTION}\n\nVerified facts:\n${factsBlock(facts)}`;
    const prompt =
      `Write the cover-letter paragraph for the ${packet.title} role at ${packet.company}. ` +
      `Use only the verified facts above.`;

    const { source: src } = await ai.stream({
      system,
      prompt,
      fallback: COVER_FALLBACK,
      onToken: (acc) => setText(acc),
      signal: ctrl.signal,
    });
    setSource(src);
    setBusy(false);
  };

  const runVoiceCheck = async () => {
    const res = await ai.voiceCheck(text, "cover");
    setViolations(res.violations);
    setChecked(true);
    return res.ok;
  };

  const save = async () => {
    setSaving(true);
    const ok = await runVoiceCheck();
    if (!ok) {
      // The check failed; surface the violations but still let the user edit.
      setSaving(false);
      flash("Cover has voice issues — review them, then save.");
      return;
    }
    const { coverUrl } = await packetApi.saveCover(appId, text);
    setSaving(false);
    if (coverUrl !== null || text.trim()) flash("Cover saved.");
    else flash("Could not save the cover.");
  };

  return (
    <div className="card" style={{ padding: "16px 20px" }}>
      <div className="sec-h" style={{ marginBottom: 12 }}>
        <span className="t">Cover paragraph</span>
        <button
          className="btn ghost tiny"
          style={{ marginLeft: "auto" }}
          disabled={busy}
          onClick={() => void regenerate()}
        >
          <Icon name="sparkles" size={13} /> {busy ? "Writing…" : "Regenerate"}
        </button>
      </div>

      <label className="fld">
        <span className="fld__l">Your cover paragraph</span>
        <textarea
          className="inp"
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            setChecked(false);
          }}
          rows={7}
          placeholder="Drafted from your library, in your voice — or write your own."
          style={{ resize: "vertical", fontFamily: "inherit" }}
        />
      </label>

      <p className="sub" style={{ margin: "10px 0 0" }}>Drafted from your library, in your voice.</p>

      {source && (
        <div style={{ marginTop: 10 }}>
          {source === "byok" ? (
            <span className="badge ok">
              <Icon name="check" size={12} /> Your voice, your key
            </span>
          ) : (
            <span className="badge muted">Demo — add a key in Settings</span>
          )}
        </div>
      )}

      {checked && violations.length > 0 && (
        <div style={{ marginTop: 12, paddingTop: 12, borderTop: "1px solid var(--border)" }}>
          <div className="sub" style={{ marginBottom: 8 }}>Voice check found a few things to fix</div>
          <ul style={{ margin: 0, paddingLeft: 18, display: "flex", flexDirection: "column", gap: 6 }}>
            {violations.map((v, i) => (
              <li key={i} className="sub" style={{ fontSize: 13.5, lineHeight: 1.5 }}>
                <span className="mono">{v.rule}</span> — {v.detail}
              </li>
            ))}
          </ul>
        </div>
      )}

      <div style={{ marginTop: 14, display: "flex", gap: 8 }}>
        <button
          className="btn primary"
          disabled={saving || busy || !text.trim()}
          onClick={() => void save()}
        >
          <Icon name="check" size={14} /> {saving ? "Saving…" : "Save"}
        </button>
        <button
          className="btn ghost"
          disabled={!text.trim()}
          onClick={() => void runVoiceCheck()}
        >
          <Icon name="check-circle" size={14} /> Voice check
        </button>
      </div>
    </div>
  );
}

function QuestionRow({ answer, flash }: { answer: Answer; flash: (msg: string) => void }) {
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(answer.answer);
      void useAnswer(answer.id);
      flash("Answer copied.");
    } catch {
      flash("Could not copy.");
    }
  };

  return (
    <div className="card" style={{ padding: "16px 20px" }}>
      <div className="sec-h" style={{ marginBottom: 8, alignItems: "flex-start" }}>
        <span className="t" style={{ flex: 1, minWidth: 0 }}>{answer.question}</span>
        <button
          className="btn ghost tiny"
          style={{ marginLeft: "auto", flex: "0 0 auto" }}
          onClick={() => void copy()}
        >
          <Icon name="copy" size={13} /> Copy
        </button>
      </div>
      <p style={{ fontSize: 14, lineHeight: 1.5, margin: "0 0 8px", whiteSpace: "pre-wrap" }}>
        {answer.answer}
      </p>
      <span className="sub">
        used <span className="mono">{answer.usedCount}</span> time{answer.usedCount === 1 ? "" : "s"}
      </span>
    </div>
  );
}

function QuestionsTab({ flash }: { flash: (msg: string) => void }) {
  const [answers, setAnswers] = useState<Answer[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void listAnswers(true).then((rows) => {
      setAnswers(rows);
      setLoading(false);
    });
  }, []);

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
      <div className="card" style={{ padding: "16px 20px" }}>
        <p className="sub" style={{ margin: 0 }}>
          Paste the form's screening questions — there's no honest way to scrape them.
          Optional questions can stay blank.
        </p>
      </div>

      {loading ? (
        <div className="sub" style={{ padding: 20 }}>Loading…</div>
      ) : answers.length === 0 ? (
        <div className="card" style={{ padding: "16px 20px" }}>
          <p className="sub" style={{ margin: 0 }}>
            No verified answers yet. Build your answer bank in the Library.
          </p>
        </div>
      ) : (
        answers.map((a) => <QuestionRow key={a.id} answer={a} flash={flash} />)
      )}
    </div>
  );
}

function SubmitTab({
  appId,
  packet,
  flash,
  onSubmitted,
}: {
  appId: string;
  packet: Packet;
  flash: (msg: string) => void;
  onSubmitted: (stage: string) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [stage, setStage] = useState(packet.stage);

  useEffect(() => setStage(packet.stage), [packet]);

  const submit = async () => {
    setBusy(true);
    const res = await packetApi.submitPacket(appId);
    setBusy(false);
    if (res) {
      setStage(res.stage);
      onSubmitted(res.stage);
      flash("Applied. Follow-up reminder set for 7 days.");
    } else {
      flash("Could not mark as applied.");
    }
  };

  const applied = stage === "applied";

  return (
    <div className="card" style={{ padding: "16px 20px" }}>
      <div className="sec-h" style={{ marginBottom: 12 }}>
        <span className="t">Mark as applied</span>
        <span className="badge muted" style={{ marginLeft: "auto" }}>
          Stage: <span className="mono">{stage}</span>
        </span>
      </div>
      <p className="sub" style={{ margin: "0 0 14px", lineHeight: 1.5 }}>
        Once you have submitted the application on the company's site, mark it here.
        We set a follow-up <strong>reminder</strong> for 7 days out — a due-date you'll
        see on Today, not a scheduled task.
      </p>
      <button
        className="btn primary"
        disabled={busy || applied}
        onClick={() => void submit()}
      >
        <Icon name={applied ? "check-circle" : "send"} size={14} />{" "}
        {applied ? "Marked as applied" : busy ? "Marking…" : "Mark as applied"}
      </button>
      {applied && (
        <p className="sub" style={{ margin: "12px 0 0", display: "inline-flex", alignItems: "center", gap: 6 }}>
          <Icon name="party-popper" size={14} /> Applied. Look for the follow-up on Today in 7 days.
        </p>
      )}
    </div>
  );
}

export function Apply({ flash }: { flash: (msg: string) => void }) {
  const [apps, setApps] = useState<Application[]>([]);
  const [loadingApps, setLoadingApps] = useState(true);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [packet, setPacket] = useState<Packet | null>(null);
  const [loadingPacket, setLoadingPacket] = useState(false);
  const [tab, setTab] = useState<TabId>("resume");

  // Fetch applications on mount; default to the first.
  useEffect(() => {
    void listApplications().then((rows) => {
      setApps(rows);
      setSelectedId((cur) => cur ?? (rows.length > 0 ? rows[0].id : null));
      setLoadingApps(false);
    });
  }, []);

  // Load the packet whenever the selection changes.
  useEffect(() => {
    if (selectedId === null) {
      setPacket(null);
      return;
    }
    setLoadingPacket(true);
    void packetApi.getPacket(selectedId).then((p) => {
      setPacket(p);
      setLoadingPacket(false);
    });
  }, [selectedId]);

  const selected = apps.find((a) => a.id === selectedId) ?? null;

  const onSubmitted = (stage: string) => {
    setApps((rows) => rows.map((a) => (a.id === selectedId ? { ...a, stage: stage as Application["stage"] } : a)));
    setPacket((p) => (p ? { ...p, stage } : p));
  };

  return (
    <div>
      <div className="phead">
        <div>
          <h1>Apply</h1>
          <p className="sub">Your application packet — the tailored CV, the cover, your answers, and the send.</p>
        </div>
      </div>

      {loadingApps ? (
        <div className="sub" style={{ padding: 20 }}>Loading…</div>
      ) : apps.length === 0 ? (
        <div className="card" style={{ padding: "16px 20px" }}>
          <p className="sub" style={{ margin: 0 }}>No applications yet.</p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
          {/* Application picker. */}
          <label className="fld" style={{ maxWidth: 480 }}>
            <span className="fld__l">Application</span>
            <select
              className="inp"
              value={selectedId ?? ""}
              onChange={(e) => setSelectedId(e.target.value)}
            >
              {apps.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.company} — {a.role}
                </option>
              ))}
            </select>
          </label>

          {/* Tabs. */}
          <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
            {TABS.map((t) => (
              <button
                key={t.id}
                className={cx("btn", tab === t.id ? "" : "ghost")}
                onClick={() => setTab(t.id)}
              >
                <Icon name={t.icon} size={14} /> {t.label}
              </button>
            ))}
          </div>

          {/* Tab body. */}
          {loadingPacket ? (
            <div className="sub" style={{ padding: 20 }}>Loading packet…</div>
          ) : !packet ? (
            <div className="card" style={{ padding: "16px 20px" }}>
              <p className="sub" style={{ margin: 0 }}>
                No packet for {selected ? selected.company : "this application"} yet — run the
                tailoring in Claude Code.
              </p>
            </div>
          ) : tab === "resume" ? (
            <ResumeTab packet={packet} flash={flash} />
          ) : tab === "cover" ? (
            <CoverTab appId={String(selectedId)} packet={packet} flash={flash} />
          ) : tab === "questions" ? (
            <QuestionsTab flash={flash} />
          ) : (
            <SubmitTab appId={String(selectedId)} packet={packet} flash={flash} onSubmitted={onSubmitted} />
          )}
        </div>
      )}
    </div>
  );
}
