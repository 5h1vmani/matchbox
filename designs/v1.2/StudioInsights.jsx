/* Matchbox — Studio Screen 6: Insights. A funnel + calibration view that answers
   "is this actually working" honestly — including saying when it's too early to tell. */

function StudioInsights({ data, momentum, patterns }) {
  const ins = data;
  const maxN = Math.max(...ins.funnel.map((f) => f.n));
  const maxReason = patterns ? Math.max(...patterns.reasons.map((r) => r.count)) : 1;

  return (
    <div>
      <div className="studio-head">
        <h1>Is this working?</h1>
        <p className="sub">Your real numbers, with an honest read on how much to trust them yet. No vanity metrics, no fake precision.</p>
      </div>

      {/* honest momentum / coach */}
      {momentum && (
        <div className="coach" style={{ marginBottom: 18 }}>
          <div className="coach__h">
            <span className="ic"><Icon name="heart-handshake" size={17} /></span>
            <span className="t">{momentum.headline}</span>
            <span className={window.cx("pacebadge", momentum.pace)}>{momentum.pace === "good" ? "healthy pace" : momentum.pace === "rest" ? "time to rest" : "room to push"}</span>
          </div>
          <div className="coach__pace">
            <div className="p"><div className="v">{momentum.thisWeek.applied}</div><div className="k">applied this week</div></div>
            <div className="p"><div className="v">{momentum.thisWeek.interviews}</div><div className="k">interviews</div></div>
            <div className="p"><div className="v">{momentum.thisWeek.followups}</div><div className="k">follow-ups</div></div>
          </div>
          <div className="coach__msg">{momentum.message}</div>
          <div style={{ marginTop: 10 }}>
            {momentum.reframes.map((r, i) => <div className="reframe" key={i}><Icon name="sparkle" size={14} /> <span>{r}</span></div>)}
          </div>
        </div>
      )}

      <div className="gridmain">
        {/* LEFT: funnel */}
        <div>
          <div className="card2 pad-card">
            <div className="sectionlabel" style={{ marginBottom: 16 }}><Icon name="filter" size={15} /> Your funnel</div>
            <div className="funnel2">
              {ins.funnel.map((f) => (
                <div className="frow2" key={f.stage}>
                  <span className="fl">{f.stage}</span>
                  <div className="ftrack">
                    <div className="ffill" style={{ width: Math.max((f.n / maxN) * 100, 7) + "%" }}>{f.n}</div>
                  </div>
                  <span className="frate">{f.rate !== null ? f.rate + "% from prev" : "\u2014"}</span>
                </div>
              ))}
            </div>
          </div>

          <div className="card2 pad-card" style={{ marginTop: 16, display: "flex", gap: 11, alignItems: "flex-start", background: "color-mix(in srgb, var(--oat-100) 30%, var(--card))" }}>
            <Icon name="compass" size={16} style={{ color: "var(--oat-600)", flex: "0 0 auto", marginTop: 1 }} />
            <div style={{ fontSize: 13.5, color: "var(--secondary-foreground)", lineHeight: 1.55 }}>{ins.note}</div>
          </div>
        </div>

        {/* RIGHT: calibration with honest confidence */}
        <div>
          <div className="sectionlabel"><Icon name="gauge" size={15} /> How much to trust each number</div>
          <div className="card2 pad-card">
            {ins.calibration.map((c, i) => (
              <div className="calib-row" key={i}>
                <div className="metricval">
                  <div className={window.scx("v", c.confidence === "low" && "dashed")}>{c.value}</div>
                  <div className="k">{c.metric}</div>
                  <div className="nsample" style={{ marginTop: 4 }}>n = {c.n}</div>
                </div>
                <div className="body">
                  <div className="topline">
                    <window.Confidence level={c.confidence} />
                  </div>
                  <div className="note2">{c.note}</div>
                  <div className="bench">{c.benchmark}</div>
                </div>
              </div>
            ))}
          </div>

          <div className="card2 pad-card" style={{ marginTop: 14, display: "flex", gap: 10, alignItems: "flex-start" }}>
            <Icon name="info" size={15} style={{ color: "var(--muted-foreground)", flex: "0 0 auto", marginTop: 1 }} />
            <div style={{ fontSize: 12.5, color: "var(--muted-foreground)", lineHeight: 1.5 }}>
              A dashed number means there isn't enough data to lean on it yet. It firms up as you apply to more roles.
            </div>
          </div>
        </div>
      </div>

      {/* learning from rejection */}
      {patterns && (
        <div style={{ marginTop: 24 }}>
          <div className="sectionlabel"><Icon name="graduation-cap" size={15} /> What your closed roles taught you <span className="sp">{patterns.closed} closed</span></div>
          <div className="gridmain">
            <div className="card2 pad-card">
              {patterns.reasons.map((r, i) => (
                <div className="reason-row" key={i}>
                  <span className="l">{r.reason}</span>
                  <span className="bar"><i style={{ width: (r.count / maxReason) * 100 + "%" }} /></span>
                  <span className="n">{r.count}</span>
                </div>
              ))}
            </div>
            <div>
              <div className="card2 pad-card" style={{ marginBottom: 14 }}>
                <div style={{ fontSize: 13.5, color: "var(--secondary-foreground)", lineHeight: 1.6 }}>{patterns.insight}</div>
              </div>
              <div className="card2 pad-card" style={{ display: "flex", gap: 10, alignItems: "flex-start", borderColor: "color-mix(in srgb, var(--oat-300) 50%, var(--border))", background: "color-mix(in srgb, var(--oat-100) 35%, var(--card))" }}>
                <Icon name="route" size={15} style={{ color: "var(--oat-600)", flex: "0 0 auto", marginTop: 1 }} />
                <div style={{ fontSize: 13, color: "var(--secondary-foreground)", lineHeight: 1.55 }}>{patterns.nudge}</div>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

window.StudioInsights = StudioInsights;
