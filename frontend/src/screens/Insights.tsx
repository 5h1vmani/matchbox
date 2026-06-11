/* Matchbox — calm honest insights. JTBD #2 support: "is my search healthy?"
   No vanity metrics, no streaks. Ported verbatim from designs/v1/Insights.jsx. */
import { useEffect, useMemo, useState } from "react";
import type { Application, Direction } from "../types";
import { Icon } from "../ui/icon";
import { Funnel, PipeBar } from "../ui/parts";
import * as iapi from "../api/insights";

// Honest framing for the weekly-pace threshold -- a read on a real count, never
// a streak or a guilt trip.
const MOMENTUM_COPY: Record<string, { tone: string; line: string }> = {
  rest: { tone: "var(--success)", line: "You have hit your pace this week. Resting is part of the work." },
  healthy: { tone: "#2f5d72", line: "Steady pace this week. You are on track." },
  push: { tone: "var(--muted-foreground)", line: "Quiet week so far. A couple more applications would keep momentum." },
};

const REASON_LABEL: Record<string, string> = {
  role_filled: "Role filled",
  not_a_fit: "Not a fit",
  comp: "Compensation",
  location: "Location",
  timing: "Timing",
  ghosted: "No response",
  withdrew: "You withdrew",
  other: "Other",
  unknown: "Not captured",
};

function MomentumPanel() {
  const [m, setM] = useState<iapi.Momentum | null>(null);
  const [reasons, setReasons] = useState<Record<string, number>>({});
  useEffect(() => {
    void iapi.getMomentum().then(setM);
    void iapi.getRejectionReasons().then(setReasons);
  }, []);
  if (!m) return null;
  const copy = MOMENTUM_COPY[m.status] ?? MOMENTUM_COPY.push;
  const reasonRows = Object.entries(reasons).sort((a, b) => b[1] - a[1]);
  return (
    <div className="momentum-grid" style={{ marginBottom: 18 }}>
      <div className="card" style={{ padding: "16px 20px" }}>
        <div className="sec-h" style={{ marginBottom: 12 }}>
          <span className="t">This week</span>
          <span className="badge muted" style={{ marginLeft: "auto" }}>last 7 days</span>
        </div>
        <div style={{ display: "flex", gap: 22 }}>
          <div><div className="mono" style={{ fontSize: 24, fontWeight: 600, color: copy.tone }}>{m.applied}</div><div className="sub">applied</div></div>
          <div><div className="mono" style={{ fontSize: 24, fontWeight: 600 }}>{m.interviews}</div><div className="sub">interviews</div></div>
          <div><div className="mono" style={{ fontSize: 24, fontWeight: 600 }}>{m.followups}</div><div className="sub">follow-ups</div></div>
        </div>
        <p className="sub" style={{ marginTop: 12 }}>{copy.line}</p>
      </div>

      <div className="card" style={{ padding: "16px 20px" }}>
        <div className="sec-h" style={{ marginBottom: 12 }}><span className="t">Why applications closed</span></div>
        {reasonRows.length === 0 ? (
          <p className="sub">Nothing closed yet. We only show reasons you have captured.</p>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 7 }}>
            {reasonRows.map(([reason, n]) => (
              <div key={reason} style={{ display: "flex", alignItems: "center", gap: 10, fontSize: 13.5 }}>
                <span>{REASON_LABEL[reason] ?? reason}</span>
                <span className="mono" style={{ marginLeft: "auto", color: "var(--muted-foreground)" }}>{n}</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function Stat({ k, v, sub, tone, icon }: {
  k: string;
  v: string | number;
  sub?: string;
  tone?: string | null;
  icon: string;
}) {
  return (
    <div className="card" style={{ padding: "16px 18px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 7, fontSize: 13, color: "var(--muted-foreground)" }}>
        <Icon name={icon} size={15} /> {k}
      </div>
      <div className="mono" style={{ fontSize: 28, fontWeight: 600, marginTop: 8, letterSpacing: "-.02em", color: tone || "var(--foreground)" }}>{v}</div>
      {sub && <div style={{ fontSize: 12.5, color: "var(--muted-foreground)", marginTop: 3 }}>{sub}</div>}
    </div>
  );
}

export function Insights({ apps, dir }: { apps: Application[]; dir: Direction }) {
  const m = useMemo(() => {
    const applied = apps.filter((a) => a.stage !== "saved").length;
    const heard = apps.filter((a) => ["phone", "onsite", "offer", "rejected"].includes(a.stage)).length;
    const interviewing = apps.filter((a) => ["phone", "onsite"].includes(a.stage)).length;
    const offers = apps.filter((a) => a.stage === "offer").length;
    const active = apps.filter((a) => ["applied", "phone", "onsite"].includes(a.stage)).length;
    const closed = apps.filter((a) => a.stage === "rejected").length;
    const cold = apps.filter((a) => a.stale).length;
    const respRate = applied ? Math.round((heard / applied) * 100) : 0;
    return { applied, heard, interviewing, offers, active, closed, cold, respRate };
  }, [apps]);

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    apps.forEach((a) => { c[a.stage] = (c[a.stage] || 0) + 1; });
    return c;
  }, [apps]);

  return (
    <div>
      <div className="phead">
        <div>
          <h1>Insights</h1>
          <p className="sub">A calm read on your search. No streaks, no pressure.</p>
        </div>
      </div>

      <MomentumPanel />

      <div className="stat-grid" style={{ marginBottom: 22 }}>
        <Stat k="Active" v={m.active} sub="still in motion" icon="activity" />
        <Stat k="Response rate" v={m.respRate + "%"} sub={m.heard + " of " + m.applied + " replied"} icon="mail" />
        <Stat k="Interviewing" v={m.interviewing} sub="phone + onsite" icon="users" tone="#2f5d72" />
        <Stat k="Offers" v={m.offers} sub={m.offers ? "on the table" : "none yet, that's ok"} icon="party-popper" tone={m.offers ? "var(--success)" : null} />
      </div>

      <div className="card" style={{ padding: "18px 20px", marginBottom: 18 }}>
        <div className="sec-h" style={{ marginBottom: 16 }}><span className="t">Where everything stands</span></div>
        {dir === "focus"
          ? <Funnel counts={counts} active="all" onPick={() => {}} />
          : <PipeBar counts={counts} total={apps.length} active="all" onPick={() => {}} />}
      </div>

      <div className="card" style={{ padding: "16px 20px", display: "flex", alignItems: "center", gap: 12 }}>
        <span className="ic" style={{ width: 32, height: 32, borderRadius: 8, background: "var(--muted)", color: "var(--muted-foreground)", display: "flex", alignItems: "center", justifyContent: "center", flex: "0 0 auto" }}>
          <Icon name="snowflake" size={16} />
        </span>
        <div style={{ fontSize: 14 }}>
          {m.cold > 0
            ? <span><b>{m.cold}</b> application{m.cold > 1 ? "s have" : " has"} gone quiet. That's normal. Follow up on the ones you still want, let the rest go.</span>
            : <span>Nothing has gone cold. You're staying on top of your follow-ups.</span>}
        </div>
      </div>
    </div>
  );
}
