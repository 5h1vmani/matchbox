/* Matchbox — Studio Screen 1: Intake & profile completeness.
   Turn a pile of uploads into a fact pool the user can trust. Show what's
   verified, what's thin, and the specific gaps the assistant is asking to fill. */
const { useState: useInState } = React;

const AREA_LEVEL = { strong: "Well evidenced", thin: "Needs more" };

function Intake({ data, gaps, completeness, flash }) {
  const [answered, setAnswered] = useInState({});
  const c = completeness;
  const trustPct = Math.round((c.verified / c.total) * 100);

  return (
    <div>
      <div className="studio-head">
        <h1>Your profile</h1>
        <p className="sub">Everything the assistant knows about you, and how sure it is. The more verified facts you have, the more honestly it can tailor.</p>
      </div>

      <div className="gridmain">
        <div>
          {/* trust meter */}
          <div className="card2 pad-card" style={{ marginBottom: 18 }}>
            <div className="trust-meter">
              <div className="trust-ring" style={{ "--p": trustPct }}>
                <span className="v">{trustPct}%</span>
              </div>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 15, fontWeight: 600, marginBottom: 10 }}>Your fact pool is mostly solid</div>
                <div className="trust-stat">
                  <div className="s"><div className="v ok">{c.verified}</div><div className="k">verified</div></div>
                  <div className="s"><div className="v thin">{c.thin}</div><div className="k">thin</div></div>
                  <div className="s"><div className="v gap">{c.gaps}</div><div className="k">gaps to fill</div></div>
                </div>
              </div>
            </div>
            <div style={{ borderTop: "1px solid var(--muted)", marginTop: 16, paddingTop: 6 }}>
              {c.areas.map((a) => (
                <div className="area-row" key={a.area}>
                  <span className="nm">{a.area}</span>
                  <span className="lvl">{a.note}</span>
                  <span className={window.scx("area-bar", a.level)}><i /></span>
                </div>
              ))}
            </div>
          </div>

          {/* gaps the assistant is asking about */}
          <div className="sectionlabel"><Icon name="message-circle-question" size={15} /> The assistant needs a few specifics
            <span className="sp">{gaps.length} open</span>
          </div>
          {gaps.map((g) => answered[g.id] ? (
            <div className="card2 pad-card" key={g.id} style={{ marginBottom: 11, display: "flex", alignItems: "center", gap: 10 }}>
              <Icon name="check-circle" size={16} style={{ color: "var(--success)" }} />
              <span style={{ fontSize: 13.5, color: "var(--muted-foreground)" }}>Thanks. That's saved to your library.</span>
            </div>
          ) : (
            <div className="gapcard" key={g.id}>
              <div className="q"><span className="ic"><Icon name="help-circle" size={17} /></span> {g.prompt}</div>
              <div className="why">{g.why}</div>
              <div className="answer">
                <input placeholder="Type a quick answer…" onKeyDown={(e) => { if (e.key === "Enter" && e.target.value.trim()) { setAnswered((s) => ({ ...s, [g.id]: true })); flash("Saved to your library"); } }} />
                <button className="btn outline small" onClick={(e) => { const inp = e.target.closest(".answer").querySelector("input"); if (inp.value.trim()) { setAnswered((s) => ({ ...s, [g.id]: true })); flash("Saved to your library"); } }}>Save</button>
              </div>
            </div>
          ))}
        </div>

        {/* RIGHT: sources */}
        <div>
          <div className="card2 pad-card">
            <div className="sectionlabel" style={{ marginBottom: 8 }}><Icon name="folder-open" size={15} /> Where this came from</div>
            {data.map((s) => (
              <div className="source-row" key={s.id}>
                <span className="ic"><Icon name={s.icon} size={17} /></span>
                <div className="info">
                  <div className="l">{s.label}</div>
                  <div className="s">
                    {s.status === "working"
                      ? <span className="working-s"><Icon name="loader" size={12} /> {s.meta}</span>
                      : s.meta}
                  </div>
                </div>
                {s.status === "processed" && <Icon name="check" size={15} style={{ color: "var(--success)", flex: "0 0 auto" }} />}
              </div>
            ))}
          </div>

          <div className="dropzone" style={{ marginTop: 14 }} onClick={() => flash("Would open a file picker")}>
            <Icon name="upload-cloud" size={22} style={{ color: "var(--muted-foreground)", margin: "0 auto" }} />
            <div className="big">Add another CV or export</div>
            <div style={{ fontSize: 12.5, marginTop: 3 }}>PDF, LinkedIn export, or paste a story. Stays on this device.</div>
          </div>

          <div className="card2 pad-card" style={{ marginTop: 14, display: "flex", gap: 10, alignItems: "flex-start" }}>
            <Icon name="lock" size={15} style={{ color: "var(--muted-foreground)", flex: "0 0 auto", marginTop: 1 }} />
            <div style={{ fontSize: 12.5, color: "var(--muted-foreground)", lineHeight: 1.5 }}>
              Your CVs and stories never leave this machine. The assistant reads them locally.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

window.Intake = Intake;
