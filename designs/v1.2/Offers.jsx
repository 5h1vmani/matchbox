/* Matchbox — Studio Screen 5: Offer & negotiation.
   Salary context (honest about low confidence), a side-by-side comparison on the
   user's own weighted priorities, and a drafted counter. */
const { useState: useOfState, useMemo: useOfMemo } = React;

function money(n) { return "$" + (n / 1000).toFixed(0) + "k"; }

function Offers({ data, flash }) {
  const o = data;
  const [weights, setWeights] = useOfState(() => Object.fromEntries(o.priorities.map((p) => [p.id, p.weight])));

  // weighted fit per offer (0-100), using the user's own weights
  const fit = useOfMemo(() => {
    const totalW = Object.values(weights).reduce((a, b) => a + b, 0) || 1;
    return o.competing.map((off) => {
      const score = o.priorities.reduce((sum, p) => sum + (off.scores[p.id] || 0) * weights[p.id], 0);
      return { id: off.id, pct: Math.round((score / (totalW * 5)) * 100) };
    });
  }, [weights, o]);
  const bestFit = Math.max(...fit.map((f) => f.pct));
  const totalComp = (off) => off.base + off.bonus;
  const bestComp = Math.max(...o.competing.map(totalComp));

  return (
    <div>
      <div className="studio-head">
        <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16 }}>
          <div>
            <h1>Your offers</h1>
            <p className="sub">Compare them on what <em>you</em> care about, not just the number. Then send a counter you're comfortable with.</p>
          </div>
          <span className="mbadge t-warn" style={{ fontSize: 12.5 }}><Icon name="clock-3" size={12} /> {o.deadline}</span>
        </div>
      </div>

      {/* comparison table */}
      <div className="card2" style={{ marginBottom: 18, overflow: "hidden" }}>
        <table className="compare">
          <thead>
            <tr>
              <th style={{ width: "26%" }}>&nbsp;</th>
              {o.competing.map((off) => (
                <th key={off.id}>
                  <div className="co"><window.Mono m={off.mono} label={off.company} size={32} radius={8} /><div><div className="nm">{off.company}</div><div className="rl">{off.role}</div></div></div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            <tr>
              <td className="metric">Base</td>
              {o.competing.map((off) => <td key={off.id}><span className="big">{money(off.base)}</span></td>)}
            </tr>
            <tr>
              <td className="metric">Bonus</td>
              {o.competing.map((off) => <td key={off.id}>{off.bonus ? money(off.bonus) : "—"}</td>)}
            </tr>
            <tr>
              <td className="metric">Equity</td>
              {o.competing.map((off) => <td key={off.id}>{off.equityNote}</td>)}
            </tr>
            <tr>
              <td className="metric">Total cash</td>
              {o.competing.map((off) => <td key={off.id}><span className={window.scx("big", totalComp(off) === bestComp && "win")}>{money(totalComp(off))}{totalComp(off) === bestComp && " ↑"}</span></td>)}
            </tr>
            <tr>
              <td className="metric">Remote</td>
              {o.competing.map((off) => <td key={off.id}>{off.remote}</td>)}
            </tr>
            <tr>
              <td className="metric">Fit to your priorities</td>
              {o.competing.map((off) => {
                const f = fit.find((x) => x.id === off.id);
                return <td key={off.id}><div className="fit-total"><span className={window.scx("v", f.pct === bestFit && "win")}>{f.pct}%</span>{f.pct === bestFit && <span className="mbadge t-ok">best for you</span>}</div></td>;
              })}
            </tr>
            <tr>
              <td className="metric">&nbsp;</td>
              {o.competing.map((off) => <td key={off.id}><span style={{ fontSize: 12.5, color: "var(--muted-foreground)" }}>{off.note}</span></td>)}
            </tr>
          </tbody>
        </table>
      </div>

      <div className="gridmain">
        {/* LEFT: priorities + salary context */}
        <div>
          <div className="card2 pad-card" style={{ marginBottom: 18 }}>
            <div className="sectionlabel" style={{ marginBottom: 6 }}><Icon name="sliders-horizontal" size={15} /> Your priorities
              <span className="sp">drag the weight, the fit updates</span>
            </div>
            {o.priorities.map((p) => (
              <div className="priority-row" key={p.id}>
                <span className="l">{p.label}</span>
                <span className="weightdots">
                  {[1, 2, 3, 4, 5].map((n) => (
                    <i key={n} className={window.scx(n <= weights[p.id] && "on")} onClick={() => setWeights((w) => ({ ...w, [p.id]: n }))} />
                  ))}
                </span>
              </div>
            ))}
          </div>

          {/* salary context — honest low confidence */}
          <div className="sectionlabel"><Icon name="banknote" size={15} /> What this role tends to pay</div>
          <div className="card2 pad-card">
            <window.Estimate
              value={money(o.salaryContext.range[0]) + "–" + money(o.salaryContext.range[1])}
              range={"Median around " + money(o.salaryContext.median) + " · " + o.salaryContext.role}
              level={o.salaryContext.confidence}
              basis={o.salaryContext.basis}
            />
          </div>
        </div>

        {/* RIGHT: counter draft */}
        <div>
          <div className="sectionlabel"><Icon name="reply" size={15} /> A counter, drafted for you</div>
          <div className="card2" style={{ overflow: "hidden" }}>
            <div className="draftcard__h" style={{ borderBottom: "1px solid var(--muted)" }}>
              <span className="ic" style={{ width: 30, height: 30, borderRadius: 8, background: "var(--oat-100)", color: "var(--oat-600)", display: "flex", alignItems: "center", justifyContent: "center" }}><Icon name="pen-line" size={15} /></span>
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 14, fontWeight: 600 }}>Counter to {o.counter.to}</div>
                <div style={{ fontSize: 12, color: "var(--muted-foreground)", marginTop: 1 }}>Asking base {money(o.counter.target)}</div>
              </div>
            </div>
            <div className="draftcard__body" style={{ maxHeight: 260 }}>{o.counter.body}</div>
            <div className="draftcard__foot">
              <button className="btn ghost small" onClick={() => flash("Opened the editor")}><Icon name="pencil" size={14} /> Edit</button>
              <span className="sp" />
              <button className="btn outline small" onClick={() => flash("Copied to clipboard")}><Icon name="copy" size={14} /> Copy</button>
              <button className="btn accent small" onClick={() => flash("Marked as sent")}><Icon name="send" size={14} /> Mark sent</button>
            </div>
          </div>
          <div className="card2 pad-card" style={{ marginTop: 14, display: "flex", gap: 10, alignItems: "flex-start" }}>
            <Icon name="info" size={15} style={{ color: "var(--muted-foreground)", flex: "0 0 auto", marginTop: 1 }} />
            <div style={{ fontSize: 12.5, color: "var(--muted-foreground)", lineHeight: 1.5 }}>
              The number comes from your competing offer and the range above. Low-confidence data is a starting point, not a script. Trust your read.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

window.Offers = Offers;
