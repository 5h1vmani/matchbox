/* Matchbox — Studio Screen 2: Search & sources setup.
   Let a non-technical person say where to look, and paste a single link or a
   raw job description to pull a role in directly. */
const { useState: useSrcState } = React;

function Sources({ sources, prefs, flash }) {
  const [srcOn, setSrcOn] = useSrcState(() => Object.fromEntries(sources.map((s) => [s.id, s.on])));
  const [paste, setPaste] = useSrcState("");
  const [link, setLink] = useSrcState("");

  const toggle = (id) => setSrcOn((s) => ({ ...s, [id]: !s[id] }));

  return (
    <div>
      <div className="studio-head">
        <h1>Where to look</h1>
        <p className="sub">Tell Matchbox where to search, or drop in a role you already found. It checks each one against your profile so you only see roles worth your time.</p>
      </div>

      <div className="gridmain">
        <div>
          {/* paste a role directly */}
          <div className="sectionlabel"><Icon name="clipboard-paste" size={15} /> Found a role already?</div>
          <div className="linkrow" style={{ marginBottom: 12 }}>
            <div className="field">
              <Icon name="link" size={16} style={{ color: "var(--muted-foreground)" }} />
              <input placeholder="Paste a job link…" value={link} onChange={(e) => setLink(e.target.value)} />
            </div>
            <button className="btn" onClick={() => { if (link.trim()) { flash("Reading that posting…"); setLink(""); } }}>Add</button>
          </div>
          <div className="paste-box">
            <textarea placeholder="…or paste the full job description here. Matchbox will pull out the title, company, and requirements." value={paste} onChange={(e) => setPaste(e.target.value)} />
            <div className="paste-box__foot">
              <span className="hint">Nothing is sent anywhere. It's parsed on this device.</span>
              <span className="sp" />
              <button className="btn accent small" disabled={!paste.trim()} onClick={() => { flash("Pulled the role from that description"); setPaste(""); }}><Icon name="sparkles" size={14} /> Pull role</button>
            </div>
          </div>

          {/* sources */}
          <div className="sectionlabel" style={{ marginTop: 26 }}><Icon name="radar" size={15} /> Sources to watch</div>
          <div className="card2 pad-card">
            {sources.map((s) => (
              <div className="src-toggle" key={s.id}>
                <div className="info">
                  <div className="nm">{s.name}</div>
                  <div className="note">{s.note}</div>
                </div>
                <button className={window.scx("switch", srcOn[s.id] && "on")} onClick={() => toggle(s.id)} aria-label={"Toggle " + s.name} />
              </div>
            ))}
          </div>
        </div>

        {/* RIGHT: what to look for */}
        <div>
          <div className="card2 pad-card">
            <div className="sectionlabel" style={{ marginBottom: 12 }}><Icon name="sliders-horizontal" size={15} /> What to look for</div>

            <div style={{ fontSize: 12.5, color: "var(--muted-foreground)", marginBottom: 8 }}>Titles</div>
            <div className="chiplist" style={{ marginBottom: 16 }}>
              {prefs.titles.map((t) => (
                <span className="editchip" key={t}>{t} <button onClick={() => flash("Would remove " + t)}><Icon name="x" size={13} /></button></span>
              ))}
              <span className="editchip add" onClick={() => flash("Would add a title")}><Icon name="plus" size={13} /> Add</span>
            </div>

            <div style={{ fontSize: 12.5, color: "var(--muted-foreground)", marginBottom: 8 }}>Locations</div>
            <div className="chiplist" style={{ marginBottom: 16 }}>
              {prefs.locations.map((t) => (
                <span className="editchip" key={t}>{t} <button onClick={() => flash("Would remove " + t)}><Icon name="x" size={13} /></button></span>
              ))}
              <span className="editchip add" onClick={() => flash("Would add a location")}><Icon name="plus" size={13} /> Add</span>
            </div>

            <div style={{ display: "flex", gap: 20 }}>
              <div>
                <div style={{ fontSize: 12.5, color: "var(--muted-foreground)", marginBottom: 6 }}>Minimum base</div>
                <div style={{ fontFamily: "var(--font-mono)", fontSize: 18, fontWeight: 600 }}>${prefs.minSalary}k</div>
              </div>
              <div>
                <div style={{ fontSize: 12.5, color: "var(--muted-foreground)", marginBottom: 6 }}>Seniority</div>
                <div style={{ fontSize: 15, fontWeight: 500, paddingTop: 1 }}>{prefs.seniority}</div>
              </div>
            </div>
          </div>

          <div className="card2 pad-card" style={{ marginTop: 14, display: "flex", gap: 10, alignItems: "flex-start" }}>
            <Icon name="info" size={15} style={{ color: "var(--oat-600)", flex: "0 0 auto", marginTop: 1 }} />
            <div style={{ fontSize: 12.5, color: "var(--secondary-foreground)", lineHeight: 1.5 }}>
              New matches show up in <b>Discover</b>, already checked for fit and eligibility. You decide there.
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

window.Sources = Sources;
