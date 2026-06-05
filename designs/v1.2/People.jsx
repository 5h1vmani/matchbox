/* Matchbox — People & referrals. Most jobs come through people. This surfaces
   who you know, which pipeline companies you have a warm path into, and drafts
   the awkward ask for you. */
const { useState: usePeState } = React;

function Person({ p, flash }) {
  return (
    <div className="personrow">
      <span className="personav" style={{ background: p.mono.bg, color: p.mono.fg }}>{p.name.split(" ").map((x) => x[0]).join("").slice(0, 2)}</span>
      <div className="info">
        <div className="nm">{p.name} <span className={window.cx("status-chip", p.status)}>{p.status === "warm" ? "warm" : p.status === "active" ? "in touch" : "cold"}</span></div>
        <div className="rl">{p.role} · {p.company} · {p.relationship}</div>
        {p.note && <div className="pnote">{p.note}</div>}
      </div>
      <div className="right">
        <span className={window.cx("strength", p.strength)}><Icon name="signal" size={11} /> {p.strength}</span>
        <span className="last">{p.lastContact === "never" ? "not yet contacted" : "last: " + p.lastContact}</span>
        <div style={{ display: "flex", gap: 5 }}>
          {p.canRefer && <button className="btn outline tiny" onClick={() => flash("Drafted a referral ask to " + p.name.split(" ")[0])}><Icon name="git-pull-request-arrow" size={13} /> Ask for referral</button>}
          <button className="iconbtn" title="Message" onClick={() => flash("Drafted a message to " + p.name.split(" ")[0])}><Icon name="mail" size={15} /></button>
        </div>
      </div>
    </div>
  );
}

function People({ people, warmPaths, introDraft, flash }) {
  const [showDraft, setShowDraft] = usePeState(false);
  const gen = window.useStream();
  const draftIt = () => { setShowDraft(true); gen.run({ task: "Drafting referral ask to " + introDraft.to, system: "You help a job-seeker write a short, warm, low-pressure referral request to someone they know. Honest, never pushy. Give them an easy out.", prompt: "Write a brief referral-ask message to " + introDraft.to + " about the Linear Senior Product Designer role. The candidate worked with them before and they previously offered to refer. Under 90 words.", fallback: introDraft.body }); };

  return (
    <div>
      <div className="studio-head">
        <h1>People</h1>
        <p className="sub">Most jobs come through someone. Here's who you know, where you have a warm path in, and the awkward ask, already drafted.</p>
      </div>

      <div className="gridmain">
        <div>
          {/* warm paths into pipeline companies */}
          <div className="warm-banner">
            <div className="warm-banner__h">
              <span style={{ width: 30, height: 30, borderRadius: 8, background: "var(--card)", border: "1px solid var(--border)", color: "var(--oat-600)", display: "flex", alignItems: "center", justifyContent: "center" }}><Icon name="route" size={16} /></span>
              <span className="t">You have a warm path into {warmPaths.length} companies you're pursuing</span>
            </div>
            {warmPaths.map((w) => (
              <div className="warmpath" key={w.company}>
                <window.Mono m={{ bg: "var(--muted)", fg: "var(--secondary-foreground)" }} label={w.company} size={30} radius={7} />
                <div className="info">
                  <div className="l"><b>{w.who}</b> at {w.company}</div>
                  <div className="s">{w.how}</div>
                </div>
                <button className="btn outline small" onClick={() => { if (w.peId === "pe1") draftIt(); else flash("Drafted an intro ask"); }}>
                  <Icon name="git-pull-request-arrow" size={14} /> Ask
                </button>
              </div>
            ))}
          </div>

          <div className="sectionlabel"><Icon name="users" size={15} /> Your network <span className="sp">{people.length} people</span></div>
          {people.map((p) => <Person key={p.id} p={p} flash={flash} />)}
        </div>

        {/* RIGHT: the drafted ask */}
        <div>
          <div className="sectionlabel"><Icon name="pen-line" size={15} /> {showDraft ? "Referral ask, drafted" : "Pick someone to ask"}</div>
          {showDraft ? (
            <div className="card2" style={{ overflow: "hidden" }}>
              <div className="draftcard__h" style={{ borderBottom: "1px solid var(--muted)" }}>
                <span className="ic" style={{ width: 30, height: 30, borderRadius: 8, background: "var(--oat-100)", color: "var(--oat-600)", display: "flex", alignItems: "center", justifyContent: "center" }}><Icon name="mail" size={15} /></span>
                <div style={{ flex: 1 }}>
                  <div style={{ fontSize: 14, fontWeight: 600 }}>To {introDraft.to}</div>
                  <div style={{ fontSize: 12, color: "var(--muted-foreground)", marginTop: 1 }}>{introDraft.subject}</div>
                </div>
              </div>
              <div className="draftcard__body" style={{ maxHeight: 280 }}>{gen.busy || gen.text ? <span className="streaming" style={{ fontSize: 13.5 }}>{gen.text}{gen.busy && <span className="cursor" />}</span> : introDraft.body}</div>
              <div className="draftcard__foot">
                {gen.source ? <window.AISource source={gen.source} /> : null}
                <button className="btn ghost small" onClick={() => flash("Opened the editor")}><Icon name="pencil" size={14} /> Edit</button>
                <span className="sp" />
                {gen.busy
                  ? <button className="btn ghost small" onClick={gen.stop}><Icon name="square" size={13} /> Stop</button>
                  : <button className="btn outline small" onClick={draftIt}><Icon name="sparkles" size={14} /> Redraft</button>}
                <button className="btn accent small" onClick={() => { flash("Logged. Reminder set to nudge in 4 days."); }}><Icon name="send" size={14} /> Mark sent</button>
              </div>
            </div>
          ) : (
            <div className="card2 pad-card" style={{ color: "var(--muted-foreground)", fontSize: 13.5, lineHeight: 1.55 }}>
              Choose <b style={{ color: "var(--foreground)" }}>Ask</b> next to a warm path and Matchbox drafts the message for you, calibrated to how well you know them. You always send it yourself.
            </div>
          )}

          <div className="card2 pad-card" style={{ marginTop: 14, display: "flex", gap: 10, alignItems: "flex-start" }}>
            <Icon name="lightbulb" size={15} style={{ color: "var(--oat-600)", flex: "0 0 auto", marginTop: 1 }} />
            <div style={{ fontSize: 12.5, color: "var(--secondary-foreground)", lineHeight: 1.55 }}>
              A referral can be 5–10x more likely to land an interview than a cold application. When you have a warm path, use it before you apply cold.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

window.People = People;
