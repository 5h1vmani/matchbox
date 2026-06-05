/* Matchbox — Studio Screen 7: Library. The editor for the reusable, verified
   sentences every tailored CV is built from. Verified vs thin shown honestly. */
const { useState: useLibState, useMemo: useLibMemo } = React;

const CATS = ["All", "Impact", "Experience", "Skill", "Education"];

function FactRow({ fact, flash }) {
  return (
    <div className={window.scx("factrow", fact.status === "thin" && "thin")}>
      <span className={window.scx("factrow__status", fact.status)}>
        <Icon name={fact.status === "verified" ? "shield-check" : "alert-triangle"} size={fact.status === "verified" ? 13 : 12} />
      </span>
      <div className="factrow__body">
        <div className="factrow__text">{fact.text}</div>
        <div className="factrow__meta">
          <span className="factrow__cat">{fact.cat}</span>
          <span className="factrow__src"><Icon name="file-text" size={12} /> {fact.sources.join(", ")}</span>
          {fact.usedIn > 0
            ? <span className="factrow__used">used in {fact.usedIn} CV{fact.usedIn > 1 ? "s" : ""}</span>
            : <span className="factrow__used" style={{ color: "var(--faint-foreground)" }}>not used yet</span>}
        </div>
        {fact.note && <div className="factrow__note"><Icon name="info" size={13} /> {fact.note}</div>}
      </div>
      <div className="factrow__acts">
        {fact.status === "thin" && <button className="btn outline tiny" onClick={() => flash("Add a source to verify this fact")}>Verify</button>}
        <button className="iconbtn" title="Edit" onClick={() => flash("Would open the sentence editor")}><Icon name="pencil" size={15} /></button>
      </div>
    </div>
  );
}

function AnswerRow({ a, flash }) {
  return (
    <div className={window.cx("qarow", a.status === "thin" && "thin")}>
      <div className="qarow__q">
        <span className="qic"><Icon name="message-circle-question" size={13} /></span>
        {a.question}
        {a.kind === "template" && <span className="opt" style={{ fontSize: 11, fontWeight: 500, color: "var(--oat-700)", background: "var(--oat-100)", borderRadius: "var(--radius-pill)", padding: "1px 8px" }}>template</span>}
        <div className="qarow__acts">
          {a.status === "thin" && <button className="btn outline tiny" onClick={() => flash("Make this answer more specific to you")}>Strengthen</button>}
          <button className="iconbtn" title="Edit" onClick={() => flash("Would open the answer editor")}><Icon name="pencil" size={15} /></button>
        </div>
      </div>
      <div className="qarow__a">{a.answer}</div>
      <div className="qarow__meta">
        {a.source && <span className="factrow__src"><Icon name="file-text" size={12} /> {a.source}</span>}
        <span className="qarow__used">used in {a.usedIn} application{a.usedIn !== 1 ? "s" : ""}</span>
      </div>
      {a.note && <div className="factrow__note" style={{ marginLeft: 32 }}><Icon name="info" size={13} /> {a.note}</div>}
    </div>
  );
}

function Library({ facts, answers, flash }) {
  const [mode, setMode] = useLibState("sentences");
  const [cat, setCat] = useLibState("All");
  const [onlyThin, setOnlyThin] = useLibState(false);

  const list = useLibMemo(() => facts.filter((f) =>
    (cat === "All" || f.cat === cat) && (!onlyThin || f.status === "thin")
  ), [facts, cat, onlyThin]);

  const verified = facts.filter((f) => f.status === "verified").length;
  const thin = facts.filter((f) => f.status === "thin").length;

  return (
    <div>
      <div className="studio-head">
        <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "space-between", gap: 16 }}>
          <div>
            <h1>Library</h1>
            <p className="sub">The verified building blocks every application is made from. Sentences for your CV, answers for the questions you get asked over and over. Keep them honest and every application stays honest.</p>
          </div>
          <button className="btn accent" onClick={() => flash(mode === "sentences" ? "Would add a new sentence" : "Would add a new answer")}><Icon name="plus" size={16} /> Add {mode === "sentences" ? "sentence" : "answer"}</button>
        </div>
      </div>

      <div className="packet-tabs" style={{ marginBottom: 18 }}>
        <button className={window.cx("packet-tab", mode === "sentences" && "active")} onClick={() => setMode("sentences")}><Icon name="text-quote" size={15} /> Sentences <span className="tnum">{facts.length}</span></button>
        <button className={window.cx("packet-tab", mode === "answers" && "active")} onClick={() => setMode("answers")}><Icon name="messages-square" size={15} /> Answers <span className="tnum">{answers.length}</span></button>
      </div>

      {mode === "answers" ? (
        <div>
          <p style={{ fontSize: 13.5, color: "var(--muted-foreground)", margin: "0 0 16px", lineHeight: 1.55, maxWidth: "66ch" }}>
            Your reusable answers to the questions every application and interview asks. Write them once; the assistant tailors the company-specific part each time. You never start from a blank box again.
          </p>
          {answers.map((a) => <AnswerRow key={a.id} a={a} flash={flash} />)}
        </div>
      ) : (
      <React.Fragment>
      <div className="lib-toolbar">
        <div className="lib-filters">
          {CATS.map((c) => <button key={c} className={window.scx(cat === c && "active")} onClick={() => setCat(c)}>{c}</button>)}
        </div>
        <span style={{ flex: 1 }} />
        <button className={window.scx("fchip", "toggle", onlyThin && "active")} onClick={() => setOnlyThin((v) => !v)} style={{ border: "1px solid var(--border)", borderRadius: "var(--radius-pill)", padding: "6px 12px", background: onlyThin ? "#f5ead9" : "var(--card)", color: onlyThin ? "#8a5a1f" : "var(--foreground)", fontSize: 13, cursor: "pointer", display: "inline-flex", alignItems: "center", gap: 7 }}>
          <Icon name="alert-triangle" size={13} /> Needs attention
        </button>
      </div>

      <div style={{ display: "flex", gap: 16, marginBottom: 16, fontSize: 13, color: "var(--muted-foreground)" }}>
        <span><b style={{ color: "var(--success)", fontFamily: "var(--font-mono)" }}>{verified}</b> verified</span>
        <span><b style={{ color: "#a65b00", fontFamily: "var(--font-mono)" }}>{thin}</b> thin, worth strengthening</span>
      </div>

      {list.length === 0
        ? <div className="quiet" style={{ border: "1px solid var(--border)", borderRadius: 12, background: "var(--card)" }}><div className="big">Nothing here.</div>Try another category.</div>
        : list.map((f) => <FactRow key={f.id} fact={f} flash={flash} />)}
      </React.Fragment>
      )}
    </div>
  );
}

window.Library = Library;
