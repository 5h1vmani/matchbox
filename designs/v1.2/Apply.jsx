/* Matchbox — Apply: the full application packet. Tailoring is no longer the end;
   it's tab one. Cover letter + screening questions get the same honest,
   provenance-backed treatment, ending in a real "submitted" state. */
const { useState: useApState } = React;

function CoverLetter({ cl, role, flash }) {
  const gen = window.useStream();
  const fallbackText = cl.paragraphs.map((p) => p.text).join("\n\n");
  const regenerate = () => gen.run({
    task: "Writing cover letter for " + (role ? role.company : "this role"),
    system: "You are a job-seeker's honest writing assistant. Write only from facts the user has verified. Never invent achievements, numbers, or claims. Warm, plain, no clichés.",
    prompt: "Write a 4-paragraph cover letter for the " + (role ? role.title + " role at " + role.company : "role") + ". Use only these verified facts: design system of 40 components used by 6 teams; checkout redesign that lifted purchases 23%; prototypes in React. Two short paragraphs may be the candidate's genuine motivation. Keep it under 180 words.",
    fallback: fallbackText,
  });
  const streamed = gen.busy || gen.text;

  return (
    <div style={{ maxWidth: 720 }}>
      <div className="guarantee" style={{ marginBottom: 18 }}>
        <span className="ic"><Icon name="shield-check" size={18} /></span>
        <div style={{ flex: 1 }}>
          <div className="t">Built from your facts and your voice.</div>
          <div className="s">The body comes from verified library facts. The two lines about why you want this are yours, marked so, and left for you to own.</div>
        </div>
      </div>
      <div className="letter">
        <div className="letter__doc">
          {streamed ? (
            <div className="streaming">{gen.text}{gen.busy && <span className="cursor" />}</div>
          ) : (
            cl.paragraphs.map((p) => (
              <p key={p.id} className={window.cx("letter__para", p.source === "your voice" && "voice")}>
                {p.text}
                <span className="src">
                  {p.source === "your voice"
                    ? <span className="voice-pill"><Icon name="user-round" size={11} /> Your voice</span>
                    : <window.Provenance>From your library</window.Provenance>}
                </span>
              </p>
            ))
          )}
        </div>
        <div className="letter__foot regen-row">
          {gen.source ? <window.AISource source={gen.source} /> : <span style={{ fontSize: 12.5, color: "var(--muted-foreground)" }}>Tuned to {role ? role.company : "the role"}. Nothing invented.</span>}
          <span className="sp" />
          {gen.busy
            ? <button className="btn ghost small" onClick={gen.stop}><Icon name="square" size={13} /> Stop</button>
            : <button className="btn outline small" onClick={regenerate}><Icon name="sparkles" size={14} /> Regenerate</button>}
          <button className="btn ghost small" onClick={() => flash("Opened the editor")}><Icon name="pencil" size={14} /> Edit</button>
          <button className="btn ghost small" onClick={() => flash("Copied to clipboard")}><Icon name="copy" size={14} /> Copy</button>
        </div>
      </div>
    </div>
  );
}

function Questions({ questions, onAnswer, flash }) {
  return (
    <div style={{ maxWidth: 720 }}>
      <p style={{ fontSize: 13.5, color: "var(--muted-foreground)", margin: "0 0 16px", lineHeight: 1.55, maxWidth: "64ch" }}>
        The questions every application asks, answered from your saved answers and profile. Optional ones we leave to you, because a real sentence beats a generated one.
      </p>
      {questions.map((q) => (
        <div className={window.cx("qcard", q.status === "needs-you" && "needs")} key={q.id}>
          <div className="qcard__q">
            {q.q}
            {q.q.includes("optional") && <span className="opt">optional</span>}
          </div>
          {q.status === "needs-you" ? (
            <React.Fragment>
              <textarea placeholder="In your own words (optional)…" defaultValue={q.answer}
                onBlur={(e) => { if (e.target.value.trim()) onAnswer(q.id); }} />
              {q.note && <div style={{ fontSize: 12.5, color: "#8a5a1f", marginTop: 8, display: "flex", gap: 7 }}><Icon name="info" size={13} style={{ flex: "0 0 auto", marginTop: 1 }} /> {q.note}</div>}
            </React.Fragment>
          ) : (
            <React.Fragment>
              <div className="qcard__a">{q.answer}</div>
              <div className="qcard__meta">
                {q.source && q.source.startsWith("answer:")
                  ? <window.Provenance>From your answers</window.Provenance>
                  : <span className="mbadge"><Icon name="user-round" size={11} /> From your profile</span>}
                {q.note && <span style={{ fontSize: 12, color: "var(--muted-foreground)" }}>{q.note}</span>}
                <span className="sp" />
                <button className="btn ghost small" onClick={() => flash("Opened the editor")}><Icon name="pencil" size={13} /> Edit</button>
              </div>
            </React.Fragment>
          )}
        </div>
      ))}
    </div>
  );
}

function Submit({ packet, answeredOptional, submitted, onSubmit, flash }) {
  const items = [
    { id: "cv", label: "Tailored résumé", sub: "9 of 12 requirements covered, honestly", done: true },
    { id: "cl", label: "Cover letter", sub: "From your facts + your voice", done: true },
    { id: "q", label: "Screening questions", sub: answeredOptional ? "All answered" : "Required answered · 1 optional left", done: true },
    { id: "portfolio", label: "Portfolio link", sub: "mayachen.design", done: true },
  ];
  if (submitted) {
    return (
      <div className="submit-wrap">
        <div className="submitted-banner">
          <span className="ring"><Icon name="check" size={24} /></span>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 16, fontWeight: 600 }}>Submitted to {packet.role.company}.</div>
            <div style={{ fontSize: 13.5, color: "#2f7a48", marginTop: 2 }}>Added to your applications and set to follow up in 7 days. Nice work.</div>
          </div>
        </div>
        <div className="card2 pad-card" style={{ marginTop: 16, display: "flex", gap: 10, alignItems: "flex-start" }}>
          <Icon name="users" size={15} style={{ color: "var(--oat-600)", flex: "0 0 auto", marginTop: 1 }} />
          <div style={{ fontSize: 13, color: "var(--secondary-foreground)", lineHeight: 1.55 }}>
            You know <b>Dana at Linear</b>. A warm referral converts far better than a cold application. Want to ask her before this sits in a queue?
          </div>
        </div>
      </div>
    );
  }
  return (
    <div className="submit-wrap">
      <p style={{ fontSize: 13.5, color: "var(--muted-foreground)", margin: "0 0 16px", lineHeight: 1.55 }}>
        Everything's ready. Review the packet, then mark it submitted once you've sent it through Linear's form. Matchbox never submits on your behalf.
      </p>
      {items.map((it) => (
        <div className="checkrow" key={it.id}>
          <span className={window.cx("checkrow__box", it.done ? "done" : "todo")}>{it.done && <Icon name="check" size={13} />}</span>
          <div style={{ flex: 1 }}>
            <div className="checkrow__t">{it.label}</div>
            <div className="checkrow__s">{it.sub}</div>
          </div>
          <Icon name="chevron-right" size={16} style={{ color: "var(--faint-foreground)" }} />
        </div>
      ))}
      <div className="submit-cta">
        <span style={{ width: 40, height: 40, borderRadius: 10, background: "var(--card)", border: "1px solid var(--border)", color: "var(--oat-600)", display: "flex", alignItems: "center", justifyContent: "center", flex: "0 0 auto" }}><Icon name="send" size={18} /></span>
        <div>
          <div className="t">Ready to apply to {packet.role.company}</div>
          <div className="s">{packet.role.title} · {packet.role.salary}</div>
        </div>
        <span className="sp" />
        <button className="btn outline" onClick={() => flash("Opened Linear's application page")}><Icon name="external-link" size={15} /> Open form</button>
        <button className="btn accent" onClick={onSubmit}><Icon name="check" size={15} /> Mark submitted</button>
      </div>
    </div>
  );
}

function Apply({ packet, tailoring, facts, flash }) {
  const [tab, setTab] = useApState("resume");
  const [answeredOptional, setAnsweredOptional] = useApState(false);
  const [submitted, setSubmitted] = useApState(false);

  const tabs = [
    { id: "resume", label: "Résumé", done: true },
    { id: "cover", label: "Cover letter", done: true },
    { id: "questions", label: "Questions", done: answeredOptional, num: answeredOptional ? null : "1" },
    { id: "submit", label: "Submit", done: submitted },
  ];

  return (
    <div>
      <div className="studio-head" style={{ marginBottom: 14 }}>
        <div style={{ display: "flex", alignItems: "center", gap: 14 }}>
          <window.Mono m={packet.role.mono} label={packet.role.company} size={46} radius={11} />
          <div style={{ flex: 1 }}>
            <h1 style={{ fontSize: 24 }}>Apply · {packet.role.company}</h1>
            <p className="sub" style={{ marginTop: 4 }}>{packet.role.title} · {packet.role.location} · {packet.role.salary}</p>
          </div>
          {submitted && <span className="mbadge t-ok" style={{ fontSize: 12.5 }}><Icon name="check" size={12} /> Submitted</span>}
        </div>
      </div>

      <div className="packet-tabs">
        {tabs.map((t) => (
          <button key={t.id} className={window.cx("packet-tab", tab === t.id && "active")} onClick={() => setTab(t.id)}>
            <span className={window.cx("tcheck", t.done ? "done" : "todo")}>{t.done && <Icon name="check" size={10} />}</span>
            {t.label}
            {t.num && <span className="tnum">{t.num}</span>}
          </button>
        ))}
      </div>

      {tab === "resume" && <window.Tailoring data={tailoring} facts={facts} flash={flash} onApply={() => setTab("cover")} embedded />}
      {tab === "cover" && <CoverLetter cl={packet.coverLetter} role={packet.role} flash={flash} />}
      {tab === "questions" && <Questions questions={packet.questions} onAnswer={() => { setAnsweredOptional(true); flash("Saved to this application and your answers"); }} flash={flash} />}
      {tab === "submit" && <Submit packet={packet} answeredOptional={answeredOptional} submitted={submitted} onSubmit={() => { setSubmitted(true); flash("Submitted to " + packet.role.company); }} flash={flash} />}
    </div>
  );
}

window.Apply = Apply;
