/* Matchbox — Studio Screen 4: Application workspace.
   A per-application home: an AI-generated interview-prep brief plus timed
   follow-up and thank-you drafts. */
const { useState: useWsState } = React;

const DRAFT_ICON = { thanks: "heart", followup: "reply" };
const DRAFT_STATUS = {
  draft: { label: "Draft", tone: "neutral" },
  scheduled: { label: "Scheduled", tone: "cool" },
  sent: { label: "Sent", tone: "ok" },
};

function Workspace({ data, rounds, flash }) {
  const w = data;
  const [status, setStatus] = useWsState(() => Object.fromEntries(w.drafts.map((d) => [d.id, d.status])));
  const [debriefs, setDebriefs] = useWsState(() => Object.fromEntries((rounds || []).map((r) => [r.id, r.debrief])));

  const logDebrief = (id, went) => {
    setDebriefs((d) => ({ ...d, [id]: { went, asked: [], notes: "" } }));
    flash("Logged. This sharpens your prep and your calibration.");
  };

  return (
    <div>
      <div className="studio-head">
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <window.Mono m={w.mono} label={w.company} size={46} radius={11} />
          <div style={{ flex: 1 }}>
            <h1 style={{ fontSize: 24 }}>{w.company}</h1>
            <p className="sub" style={{ marginTop: 4 }}>{w.title} · <span className="mbadge t-cool" style={{ verticalAlign: "middle" }}>{w.stage}</span> · next: {w.nextDate}</p>
          </div>
          <button className="btn outline" onClick={() => flash("Opened in the tracker")}><Icon name="external-link" size={15} /> In tracker</button>
        </div>
      </div>

      {/* interview loop */}
      {rounds && rounds.length > 0 && (
        <div style={{ marginBottom: 24 }}>
          <div className="sectionlabel"><Icon name="git-branch" size={15} /> Interview loop
            <span className="sp">{rounds.filter((r) => r.status === "done").length} of {rounds.length} rounds done</span>
          </div>
          <div className="card2 pad-card">
            {rounds.map((r) => {
              const db = debriefs[r.id];
              const needsDebrief = r.status === "done" && !db;
              return (
                <div className="round" key={r.id}>
                  <span className={window.cx("round__dot", r.status)}>
                    <Icon name={r.status === "done" ? "check" : r.status === "upcoming" ? "calendar-clock" : "circle"} size={r.status === "pending" ? 8 : 15} />
                  </span>
                  <div className="round__body">
                    <div className="round__top">
                      <span className="round__label">{r.label}</span>
                      <span className="round__when">{r.when}</span>
                    </div>
                    <div className="round__who">{r.who} · {r.role}</div>
                    <div className="round__focus">{r.focus}</div>

                    {r.status === "upcoming" && (
                      <div style={{ marginTop: 9, display: "flex", gap: 8 }}>
                        <button className="btn accent small" onClick={() => flash("Opened prep for this round")}><Icon name="clipboard-list" size={13} /> Prep this round</button>
                      </div>
                    )}
                    {needsDebrief && (
                      <div className="debrief-prompt">
                        <div className="t">How did this round go? A quick note sharpens your next prep and your numbers.</div>
                        <div className="opts">
                          <button className="debrief-opt" onClick={() => logDebrief(r.id, "well")}><Icon name="smile" size={14} style={{ color: "#1d7a40" }} /> Went well</button>
                          <button className="debrief-opt" onClick={() => logDebrief(r.id, "ok")}><Icon name="meh" size={14} style={{ color: "#a65b00" }} /> Hard to read</button>
                          <button className="debrief-opt" onClick={() => logDebrief(r.id, "poorly")}><Icon name="frown" size={14} style={{ color: "var(--muted-foreground)" }} /> Rough</button>
                        </div>
                      </div>
                    )}
                    {db && (
                      <div className="debrief-done">
                        <div className="went">{db.went === "well" ? "Went well" : db.went === "ok" ? "Hard to read" : "Felt rough"}{db.asked && db.asked.length ? " · they asked:" : ""}</div>
                        {db.asked && db.asked.length > 0 && <div className="asked">{db.asked.map((q, i) => <span key={i}><b>{q}</b>{i < db.asked.length - 1 ? " · " : ""}</span>)}</div>}
                        {db.notes && <div className="asked">{db.notes}</div>}
                      </div>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        </div>
      )}

      <div className="gridmain">
        {/* LEFT: prep brief */}
        <div>
          <div className="sectionlabel">
            <Icon name="clipboard-list" size={15} /> Interview prep brief
            <span className="sp"><window.Provenance>Generated {w.prep.generatedDaysAgo}d ago</window.Provenance></span>
          </div>

          <div className="card2 pad-card" style={{ marginBottom: 14 }}>
            <div className="prep-section">
              <h4>About them</h4>
              <p style={{ fontSize: 14, lineHeight: 1.6, color: "var(--zinc-700)", margin: 0 }}>{w.prep.about}</p>
            </div>
          </div>

          <div className="card2 pad-card" style={{ marginBottom: 14 }}>
            <div className="prep-section">
              <h4>Likely questions</h4>
              {w.prep.questions.map((q, i) => (
                <div className="qa" key={i}>
                  <div className="qa__q"><span className="ic"><Icon name="message-square" size={15} /></span> {q.q}</div>
                  <div className="qa__hint"><b>Your angle:</b> {q.hint}</div>
                </div>
              ))}
            </div>
          </div>

          <div className="gridtwo">
            <div className="card2 pad-card">
              <div className="prep-section" style={{ margin: 0 }}>
                <h4>Lead with</h4>
                <div className="talklist">
                  {w.prep.talking.map((t, i) => <div className="t" key={i}><span className="d" /> {t}</div>)}
                </div>
              </div>
            </div>
            <div className="card2 pad-card">
              <div className="prep-section" style={{ margin: 0 }}>
                <h4>Watch out for</h4>
                <div className="watchlist2">
                  {w.prep.watch.map((t, i) => <div className="w" key={i}><Icon name="alert-triangle" size={14} /> {t}</div>)}
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* RIGHT: timed drafts */}
        <div>
          <div className="sectionlabel"><Icon name="mail" size={15} /> Drafts, timed for you</div>
          {w.drafts.map((d) => {
            const st = status[d.id];
            const meta = DRAFT_STATUS[st];
            return (
              <div className="draftcard" key={d.id}>
                <div className="draftcard__h">
                  <span className="ic"><Icon name={DRAFT_ICON[d.kind]} size={15} /></span>
                  <div style={{ flex: 1 }}>
                    <div className="t">{d.title}</div>
                    <div className="timing"><Icon name="clock-3" size={11} /> {d.timing}</div>
                  </div>
                  <window.Badge tone={meta.tone}>{meta.label}</window.Badge>
                </div>
                <div className="draftcard__body">{d.body}</div>
                <div className="draftcard__foot">
                  <button className="btn ghost small" onClick={() => flash("Opened the editor")}><Icon name="pencil" size={14} /> Edit</button>
                  <span className="sp" />
                  {st !== "sent" && <button className="btn outline small" onClick={() => { setStatus((s) => ({ ...s, [d.id]: st === "scheduled" ? "draft" : "scheduled" })); flash(st === "scheduled" ? "Unscheduled" : "Scheduled to send"); }}>
                    <Icon name={st === "scheduled" ? "calendar-x" : "calendar-clock"} size={14} /> {st === "scheduled" ? "Unschedule" : "Schedule"}
                  </button>}
                  <button className="btn accent small" onClick={() => { setStatus((s) => ({ ...s, [d.id]: "sent" })); flash("Sent to " + w.company); }} disabled={st === "sent"}>
                    <Icon name="send" size={14} /> {st === "sent" ? "Sent" : "Send now"}
                  </button>
                </div>
              </div>
            );
          })}

          <div className="card2 pad-card" style={{ display: "flex", gap: 10, alignItems: "flex-start" }}>
            <Icon name="sparkles" size={15} style={{ color: "var(--oat-600)", flex: "0 0 auto", marginTop: 1 }} />
            <div style={{ fontSize: 12.5, color: "var(--secondary-foreground)", lineHeight: 1.5 }}>
              The assistant drafts these from your notes and the role. It never sends on its own. You always send.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

window.Workspace = Workspace;
