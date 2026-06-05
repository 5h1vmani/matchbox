/* Matchbox — calm honest insights. JTBD #2 support: "is my search healthy?"
   No vanity metrics, no streaks. Just the few numbers that help you decide. */
const { useMemo: useInsMemo } = React;

function Stat({ k, v, sub, tone, icon }) {
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

function Insights({ apps, dir }) {
  const m = useInsMemo(() => {
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

  const counts = useInsMemo(() => { const c = {}; apps.forEach((a) => c[a.stage] = (c[a.stage] || 0) + 1); return c; }, [apps]);

  return (
    <div>
      <div className="phead">
        <div>
          <h1>Insights</h1>
          <p className="sub">A calm read on your search. No streaks, no pressure.</p>
        </div>
      </div>

      <div style={{ display: "grid", gridTemplateColumns: "repeat(4, 1fr)", gap: 16, marginBottom: 22 }}>
        <Stat k="Active" v={m.active} sub="still in motion" icon="activity" />
        <Stat k="Response rate" v={m.respRate + "%"} sub={m.heard + " of " + m.applied + " replied"} icon="mail" />
        <Stat k="Interviewing" v={m.interviewing} sub="phone + onsite" icon="users" tone="#2f5d72" />
        <Stat k="Offers" v={m.offers} sub={m.offers ? "on the table" : "none yet, that's ok"} icon="party-popper" tone={m.offers ? "var(--success)" : null} />
      </div>

      <div className="card" style={{ padding: "18px 20px", marginBottom: 18 }}>
        <div className="sec-h" style={{ marginBottom: 16 }}><span className="t">Where everything stands</span></div>
        {dir === "focus"
          ? <window.Funnel counts={counts} active="all" onPick={() => {}} />
          : <window.PipeBar counts={counts} total={apps.length} active="all" onPick={() => {}} />}
      </div>

      <div className="card" style={{ padding: "16px 20px", display: "flex", alignItems: "center", gap: 12 }}>
        <span className="ic" style={{ width: 32, height: 32, borderRadius: 8, background: "var(--muted)", color: "var(--muted-foreground)", display: "flex", alignItems: "center", justifyContent: "center", flex: "0 0 auto" }}><Icon name="snowflake" size={16} /></span>
        <div style={{ fontSize: 14 }}>
          {m.cold > 0
            ? <span><b>{m.cold}</b> application{m.cold > 1 ? "s have" : " has"} gone quiet. That's normal. Follow up on the ones you still want, let the rest go.</span>
            : <span>Nothing has gone cold. You're staying on top of your follow-ups.</span>}
        </div>
      </div>
    </div>
  );
}

window.Insights = Insights;
