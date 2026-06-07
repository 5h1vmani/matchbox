/* Matchbox — interview-loop Workspace. JTBD: keep track of the rounds in flight
   for an application and what each one felt like. Rounds are MANUAL ENTRY — there
   is no calendar / ATS / email sync, so the copy says so plainly. Debriefs are
   shown beside their round exactly as captured; we never compute an aggregate or
   "calibrated" statistic from them. */
import { useEffect, useState } from "react";
import type { Application } from "../types";
import { listApplications } from "../api/client";
import * as rounds from "../api/interviews";
import { cx } from "../lib/derive";
import { Icon } from "../ui/icon";

// Stages where an interview loop is actually running (per the screen contract).
const INTERVIEWING: ReadonlyArray<string> = ["phone", "onsite", "offer"];

const KIND_OPTIONS: ReadonlyArray<{ id: rounds.RoundKind; label: string }> = [
  { id: "recruiter", label: "Recruiter screen" },
  { id: "hm", label: "Hiring manager" },
  { id: "technical", label: "Technical" },
  { id: "onsite", label: "Onsite" },
  { id: "values", label: "Values / culture" },
  { id: "other", label: "Other" },
];

const KIND_LABEL: Record<string, string> = {
  recruiter: "Recruiter screen",
  hm: "Hiring manager",
  technical: "Technical",
  onsite: "Onsite",
  values: "Values / culture",
  other: "Other",
};

const STATUS_LABEL: Record<string, string> = {
  scheduled: "Scheduled",
  done: "Done",
  cancelled: "Cancelled",
};

const SENTIMENT_OPTIONS: ReadonlyArray<{ id: rounds.DebriefSentiment; label: string }> = [
  { id: "good", label: "Good" },
  { id: "mixed", label: "Mixed" },
  { id: "tough", label: "Tough" },
];

const SENTIMENT_LABEL: Record<string, string> = {
  good: "Good",
  mixed: "Mixed",
  tough: "Tough",
  unknown: "Not rated",
};

function whenText(scheduledAt: string | null): string {
  if (!scheduledAt) return "not dated";
  const d = new Date(scheduledAt);
  if (Number.isNaN(d.getTime())) return scheduledAt;
  return d.toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" });
}

function statusTone(status: string): "ok" | "muted" {
  return status === "done" ? "ok" : "muted";
}

/* One round in the timeline: kind, date, status, focus, plus its debrief (if
   present) and one-tap debrief capture (if not). */
function RoundRow({
  round,
  onDebrief,
  onDelete,
}: {
  round: rounds.Round;
  onDebrief: (id: number, body: rounds.DebriefCreate) => void;
  onDelete: (id: number) => void;
}) {
  const [sentiment, setSentiment] = useState<rounds.DebriefSentiment | null>(null);
  const [notes, setNotes] = useState<string>("");

  const submitDebrief = () => {
    const body: rounds.DebriefCreate = {};
    if (sentiment) body.sentiment = sentiment;
    if (notes.trim()) body.notes = notes.trim();
    onDebrief(round.id, body);
    setSentiment(null);
    setNotes("");
  };

  return (
    <div className="card" style={{ padding: "16px 20px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 10 }}>
        <span style={{ fontWeight: 600 }}>{KIND_LABEL[round.kind] ?? round.kind}</span>
        <span className={cx("badge", statusTone(round.status))}>{STATUS_LABEL[round.status] ?? round.status}</span>
        <span className="sub mono" style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
          <Icon name="calendar" size={13} /> {whenText(round.scheduledAt)}
        </span>
        <button
          className="btn tiny ghost"
          style={{ marginLeft: "auto" }}
          title="Delete round"
          onClick={() => onDelete(round.id)}
        >
          <Icon name="trash-2" size={14} /> Delete
        </button>
      </div>

      {round.focus && <p className="sub" style={{ marginTop: 8 }}>{round.focus}</p>}

      {round.debrief ? (
        /* Debrief shown side-by-side with the round, exactly as captured. */
        <div
          style={{
            display: "flex",
            gap: 14,
            marginTop: 12,
            paddingTop: 12,
            borderTop: "1px solid var(--border)",
          }}
        >
          <div style={{ flex: "0 0 auto" }}>
            <div className="sub">Sentiment</div>
            <span
              className={cx(
                "badge",
                round.debrief.sentiment === "good"
                  ? "ok"
                  : "muted"
              )}
              style={{ marginTop: 4 }}
            >
              {SENTIMENT_LABEL[round.debrief.sentiment ?? "unknown"] ?? round.debrief.sentiment}
            </span>
          </div>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div className="sub">Notes</div>
            <div style={{ marginTop: 4, fontSize: 13.5 }}>
              {round.debrief.notes ? round.debrief.notes : <span className="sub">No notes.</span>}
            </div>
          </div>
        </div>
      ) : (
        /* One-tap debrief capture. */
        <div
          style={{
            marginTop: 12,
            paddingTop: 12,
            borderTop: "1px solid var(--border)",
            display: "flex",
            flexDirection: "column",
            gap: 8,
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
            <span className="sub">How did it go?</span>
            {SENTIMENT_OPTIONS.map((s) => (
              <button
                key={s.id}
                className={cx("btn tiny", sentiment === s.id ? "" : "ghost")}
                onClick={() => setSentiment(sentiment === s.id ? null : s.id)}
              >
                {s.label}
              </button>
            ))}
          </div>
          <input
            className="inp"
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Optional notes — what was asked, how it felt…"
          />
          <button
            className="btn tiny"
            style={{ alignSelf: "flex-start" }}
            disabled={!sentiment && !notes.trim()}
            onClick={submitDebrief}
          >
            <Icon name="check" size={14} /> Save debrief
          </button>
        </div>
      )}
    </div>
  );
}

/* Add-round form: kind (required), optional date, optional focus. */
function AddRound({ onAdd }: { onAdd: (body: rounds.RoundCreate) => void }) {
  const [kind, setKind] = useState<rounds.RoundKind>("recruiter");
  const [scheduledAt, setScheduledAt] = useState<string>("");
  const [focus, setFocus] = useState<string>("");

  const submit = () => {
    const body: rounds.RoundCreate = { kind };
    if (scheduledAt) body.scheduledAt = scheduledAt;
    if (focus.trim()) body.focus = focus.trim();
    onAdd(body);
    setScheduledAt("");
    setFocus("");
  };

  return (
    <div className="card" style={{ padding: "16px 20px" }}>
      <div className="sec-h" style={{ marginBottom: 12 }}>
        <span className="t">Add a round</span>
      </div>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
        <label className="fld" style={{ flex: "1 1 160px" }}>
          <span className="fld__l">Kind</span>
          <select
            className="inp"
            value={kind}
            onChange={(e) => setKind(e.target.value as rounds.RoundKind)}
          >
            {KIND_OPTIONS.map((k) => (
              <option key={k.id} value={k.id}>
                {k.label}
              </option>
            ))}
          </select>
        </label>
        <label className="fld" style={{ flex: "0 1 170px" }}>
          <span className="fld__l">Date (optional)</span>
          <input
            className="inp"
            type="date"
            value={scheduledAt}
            onChange={(e) => setScheduledAt(e.target.value)}
          />
        </label>
        <label className="fld" style={{ flex: "2 1 220px" }}>
          <span className="fld__l">Focus (optional)</span>
          <input
            className="inp"
            value={focus}
            onChange={(e) => setFocus(e.target.value)}
            placeholder="System design, behavioural…"
          />
        </label>
        <button className="btn" onClick={submit}>
          <Icon name="plus" size={15} /> Add round
        </button>
      </div>
    </div>
  );
}

export function Workspace({ flash }: { flash: (msg: string) => void }) {
  const [apps, setApps] = useState<Application[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [list, setList] = useState<rounds.Round[]>([]);

  // Fetch applications on mount; narrow to interviewing stages.
  useEffect(() => {
    void listApplications().then((all) => {
      const inFlight = all.filter((a) => INTERVIEWING.includes(a.stage));
      setApps(inFlight);
      setSelectedId((cur) => cur ?? (inFlight.length > 0 ? inFlight[0].id : null));
    });
  }, []);

  // Load rounds whenever the selected application changes.
  useEffect(() => {
    if (selectedId === null) {
      setList([]);
      return;
    }
    void rounds.listRounds(selectedId).then(setList);
  }, [selectedId]);

  const refresh = (appId: string) => {
    void rounds.listRounds(appId).then(setList);
  };

  const selected = apps.find((a) => a.id === selectedId) ?? null;

  const addRound = (body: rounds.RoundCreate) => {
    if (!selectedId) return;
    void rounds.createRound(selectedId, body).then((r) => {
      if (r) {
        flash("Round added — " + (KIND_LABEL[r.kind] ?? r.kind));
        refresh(selectedId);
      } else {
        flash("Could not add the round.");
      }
    });
  };

  const debrief = (id: number, body: rounds.DebriefCreate) => {
    if (!selectedId) return;
    void rounds.captureDebrief(id, body).then((r) => {
      if (r) {
        flash("Debrief saved.");
        refresh(selectedId);
      } else {
        flash("Could not save the debrief.");
      }
    });
  };

  const remove = (id: number) => {
    if (!selectedId) return;
    void rounds.deleteRound(id).then((ok) => {
      if (ok) {
        flash("Round deleted.");
        refresh(selectedId);
      } else {
        flash("Could not delete the round.");
      }
    });
  };

  return (
    <div>
      <div className="phead">
        <div>
          <h1>Workspace</h1>
          <p className="sub">Add rounds yourself — there is no calendar sync.</p>
        </div>
      </div>

      {apps.length === 0 ? (
        <div className="card" style={{ padding: "16px 20px" }}>
          <p className="sub">No interviews in flight yet.</p>
        </div>
      ) : (
        <div style={{ display: "grid", gridTemplateColumns: "240px 1fr", gap: 16, alignItems: "start" }}>
          {/* Left: interviewing applications. */}
          <div className="card" style={{ padding: "16px 20px" }}>
            <div className="sec-h" style={{ marginBottom: 12 }}>
              <span className="t">Interviewing</span>
            </div>
            <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
              {apps.map((a) => (
                <button
                  key={a.id}
                  className={cx("btn", a.id === selectedId ? "" : "ghost")}
                  style={{ justifyContent: "flex-start", textAlign: "left" }}
                  onClick={() => setSelectedId(a.id)}
                >
                  <span style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
                    <span style={{ fontWeight: 600 }}>{a.company}</span>
                    <span className="sub" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>
                      {a.role}
                    </span>
                  </span>
                </button>
              ))}
            </div>
          </div>

          {/* Right: selected application's rounds. */}
          <div style={{ display: "flex", flexDirection: "column", gap: 16 }}>
            {selected && (
              <div className="sec-h">
                <span className="t" style={{ display: "inline-flex", alignItems: "center", gap: 7 }}>
                  <Icon name="users" size={15} /> {selected.company} — {selected.role}
                </span>
              </div>
            )}

            <AddRound onAdd={addRound} />

            {list.length === 0 ? (
              <div className="card" style={{ padding: "16px 20px" }}>
                <p className="sub">No rounds logged. Add the first one.</p>
              </div>
            ) : (
              list.map((r) => (
                <RoundRow key={r.id} round={r} onDebrief={debrief} onDelete={remove} />
              ))
            )}
          </div>
        </div>
      )}
    </div>
  );
}
