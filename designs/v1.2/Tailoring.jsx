/* Matchbox — Studio Screen 3: Tailoring review / "ready to apply".
   The highest-stakes surface. Trust is built from provenance + honest gaps:
   every changed line traces to a verified Library fact; requirements it could
   not back are shown empty, never fabricated. */
const { useState: useTlState } = React;

const REQ_ICON = { covered: "check", partial: "minus", empty: "circle" };

function DiffLine({ d, factText }) {
  const flagged = !!d.flag;
  return (
    <div className={window.scx("diffline", flagged && "flagged")}>
      <div className="diffline__head">
        <span className={window.scx("diffline__tag", d.kind)}>
          {d.kind === "rephrased" ? "Rephrased" : d.kind === "added" ? "Added" : "Kept"}
        </span>
        <span className="sp" />
        {d.source && <window.Provenance>From your library</window.Provenance>}
      </div>
      <div className="diffline__body">
        {d.before && <div className="diff-before">{d.before}</div>}
        <div className="diff-after">{d.after}</div>
        {d.note && (
          <div className="diffline__note">
            <Icon name={flagged ? "alert-triangle" : "info"} size={14} />
            <span>{d.note}</span>
          </div>
        )}
      </div>
    </div>
  );
}

function Tailoring({ data, facts, flash, onApply }) {
  const t = data;
  const [tab, setTab] = useTlState("changes");
  const factById = (id) => (facts.find((f) => f.id === id) || {}).text;

  const covered = t.requirements.filter((r) => r.status === "covered").length;
  const partial = t.requirements.filter((r) => r.status === "partial").length;
  const empty = t.requirements.filter((r) => r.status === "empty").length;

  return (
    <div>
      <div className="studio-head">
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <window.Mono m={t.role.mono} label={t.role.company} size={46} radius={11} />
          <div style={{ flex: 1 }}>
            <h1 style={{ fontSize: 24 }}>Ready to apply · {t.role.company}</h1>
            <p className="sub" style={{ marginTop: 4 }}>{t.role.title} · {t.role.location} · {t.role.salary}</p>
          </div>
        </div>
      </div>

      {/* the trust guarantee — the emotional core */}
      <div className="guarantee">
        <span className="ic"><Icon name="shield-check" size={18} /></span>
        <div style={{ flex: 1 }}>
          <div className="t">Nothing here was made up.</div>
          <div className="s">Every change below is rephrased from a fact you already verified. Where your library had no proof, we left it empty instead of inventing something.</div>
        </div>
      </div>

      <div className="gridmain">
        {/* LEFT: the diff */}
        <div>
          <div className="sectionlabel">
            <Icon name="file-diff" size={15} /> What changed in your CV
            <span className="sp" />
            <div className="lib-filters" style={{ padding: 3 }}>
              <button className={window.scx(tab === "changes" && "active")} onClick={() => setTab("changes")}>Changes</button>
              <button className={window.scx(tab === "all" && "active")} onClick={() => setTab("all")}>Full CV</button>
            </div>
          </div>
          {t.diff
            .filter((d) => tab === "all" ? true : d.kind !== "kept" || d.note)
            .map((d) => <DiffLine key={d.id} d={d} factText={factById(d.source)} />)}

          <div className="card2 pad-card" style={{ marginTop: 4, display: "flex", alignItems: "center", gap: 12 }}>
            <Icon name="sparkles" size={16} style={{ color: "var(--oat-600)", flex: "0 0 auto" }} />
            <div style={{ flex: 1, fontSize: 13, color: "var(--secondary-foreground)", lineHeight: 1.5 }}>
              {t.summary.changed} lines rephrased, {t.summary.added} added, {t.summary.kept} kept. All from your verified library.
            </div>
          </div>
        </div>

        {/* RIGHT: coverage panel (sticky) */}
        <div className="coverwrap">
          <div className="card2 pad-card">
            <div className="sectionlabel" style={{ marginBottom: 6 }}><Icon name="list-checks" size={15} /> Requirements covered</div>
            <div style={{ display: "flex", alignItems: "baseline", gap: 8, margin: "6px 0 2px" }}>
              <span style={{ fontFamily: "var(--font-mono)", fontSize: 24, fontWeight: 600 }}>{t.summary.requirementsCovered}<span style={{ color: "var(--faint-foreground)" }}>/{t.summary.requirementsTotal}</span></span>
              <span style={{ fontSize: 13, color: "var(--muted-foreground)" }}>met by your real experience</span>
            </div>
            <div className="coverbar">
              <div className="seg covered" style={{ flex: covered }} />
              <div className="seg partial" style={{ flex: partial }} />
              <div className="seg empty" style={{ flex: empty }} />
            </div>

            {t.requirements.map((r) => (
              <div className={window.scx("req", "is-" + r.status)} key={r.id}>
                <span className={window.scx("req__ic", r.status)}><Icon name={REQ_ICON[r.status]} size={r.status === "empty" ? 8 : 11} /></span>
                <div style={{ flex: 1 }}>
                  <div className="req__t">{r.text}</div>
                  <div className="req__how">{r.how}</div>
                </div>
              </div>
            ))}

            <div className="cover-legend">
              <span className="k"><span className="d" style={{ background: "var(--success)" }} /> Covered</span>
              <span className="k"><span className="d" style={{ background: "#d9a441" }} /> Partial</span>
              <span className="k"><span className="d" style={{ background: "var(--zinc-300)" }} /> Left empty</span>
            </div>
          </div>

          {/* honest gaps callout */}
          <div className="card2 pad-card" style={{ marginTop: 14, borderColor: "#ecdcc0", background: "#fdfaf4" }}>
            <div style={{ display: "flex", gap: 9 }}>
              <Icon name="circle-off" size={16} style={{ color: "#a65b00", flex: "0 0 auto", marginTop: 1 }} />
              <div>
                <div style={{ fontSize: 13.5, fontWeight: 600, color: "#8a5a1f" }}>{empty} requirements left empty</div>
                <div style={{ fontSize: 12.5, color: "#8a6a3a", marginTop: 4, lineHeight: 1.5 }}>
                  We couldn't back these from your library, so we didn't claim them. Add evidence in your Library to close them honestly.
                </div>
              </div>
            </div>
          </div>

          <div style={{ display: "flex", gap: 9, marginTop: 16 }}>
            <button className="btn outline" style={{ flex: 1 }} onClick={() => flash("Opened the editable CV")}><Icon name="pencil" size={15} /> Edit</button>
            <button className="btn accent" style={{ flex: 1 }} onClick={() => { onApply && onApply(); flash("Saved. Added to your applications."); }}><Icon name="check" size={15} /> Looks honest, use it</button>
          </div>
        </div>
      </div>
    </div>
  );
}

window.Tailoring = Tailoring;
