/* Matchbox — Library answers. A calm, reusable Q&A bank: the application
   questions you answer once (why us, salary expectations, work authorization)
   and reach for again across every job. Honest throughout — unfilled answers
   read as needs-you, never fabricated. The screen only renders what was
   measured; usage counts and verification come straight from the server. */
import { useEffect, useState } from "react";
import * as api from "../api/answers";
import { cx } from "../lib/derive";
import { Icon } from "../ui/icon";

function AnswerRow({
  answer,
  flash,
  onChange,
  onRemove,
}: {
  answer: api.Answer;
  flash: (msg: string) => void;
  onChange: (a: api.Answer) => void;
  onRemove: (id: number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(answer.answer);
  const [busy, setBusy] = useState(false);

  const toggleVerified = async () => {
    setBusy(true);
    const next = !answer.verified;
    const updated = await api.updateAnswer(answer.id, { verified: next });
    setBusy(false);
    if (updated) {
      onChange(updated);
      flash(next ? "Verified." : "Marked unverified.");
    }
  };

  const saveEdit = async () => {
    const text = draft.trim();
    if (!text || text === answer.answer) {
      setEditing(false);
      setDraft(answer.answer);
      return;
    }
    setBusy(true);
    const updated = await api.updateAnswer(answer.id, { answer: text });
    setBusy(false);
    if (updated) {
      onChange(updated);
      setEditing(false);
      flash("Answer updated.");
    }
  };

  const remove = async () => {
    setBusy(true);
    const ok = await api.deleteAnswer(answer.id);
    setBusy(false);
    if (ok) {
      onRemove(answer.id);
      flash("Answer removed.");
    }
  };

  const hasAnswer = answer.answer.trim().length > 0;

  return (
    <div className="card" style={{ padding: "16px 20px" }}>
      <div className="sec-h" style={{ marginBottom: 10, alignItems: "flex-start" }}>
        <span className="t" style={{ flex: 1, minWidth: 0 }}>{answer.question}</span>
        <span className={cx("badge", answer.verified ? "ok" : "muted")} style={{ marginLeft: "auto", flex: "0 0 auto" }}>
          {answer.verified ? "Verified" : "Unverified"}
        </span>
      </div>

      {editing ? (
        <div className="fld" style={{ marginBottom: 10 }}>
          <span className="fld__l">Answer</span>
          <textarea
            className="inp"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            rows={4}
            style={{ resize: "vertical", fontFamily: "inherit" }}
          />
          <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
            <button className="btn tiny" disabled={busy} onClick={() => void saveEdit()}>
              <Icon name="check" size={13} /> Save
            </button>
            <button
              className="btn ghost tiny"
              disabled={busy}
              onClick={() => { setEditing(false); setDraft(answer.answer); }}
            >
              <Icon name="x" size={13} /> Cancel
            </button>
          </div>
        </div>
      ) : hasAnswer ? (
        <p style={{ fontSize: 14, lineHeight: 1.5, margin: "0 0 10px", whiteSpace: "pre-wrap" }}>{answer.answer}</p>
      ) : (
        <p className="sub" style={{ margin: "0 0 10px" }}>Not answered yet. Add your own words when you are ready.</p>
      )}

      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        {answer.category && <span className="badge muted">{answer.category}</span>}
        <span className="sub">used <span className="mono">{answer.usedCount}</span> time{answer.usedCount === 1 ? "" : "s"}</span>
        {answer.sourceFile && (
          <span className="sub" style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
            <Icon name="book-open" size={13} /> {answer.sourceFile}
          </span>
        )}
        {!editing && (
          <div style={{ display: "flex", gap: 8, marginLeft: "auto" }}>
            <button className="btn ghost tiny" disabled={busy} onClick={() => void toggleVerified()}>
              <Icon name={answer.verified ? "x" : "check-circle"} size={13} />
              {answer.verified ? " Mark unverified" : " Verify"}
            </button>
            <button className="btn ghost tiny" disabled={busy} onClick={() => { setDraft(answer.answer); setEditing(true); }}>
              <Icon name="edit-3" size={13} /> Edit
            </button>
            <button className="btn ghost tiny" disabled={busy} onClick={() => void remove()}>
              <Icon name="trash-2" size={13} /> Delete
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export function Answers({ flash }: { flash: (msg: string) => void }) {
  const [answers, setAnswers] = useState<api.Answer[]>([]);
  const [loading, setLoading] = useState(true);

  const [question, setQuestion] = useState("");
  const [answerText, setAnswerText] = useState("");
  const [category, setCategory] = useState("");
  const [adding, setAdding] = useState(false);

  useEffect(() => {
    void api.listAnswers().then((rows) => {
      setAnswers(rows);
      setLoading(false);
    });
  }, []);

  const onChange = (updated: api.Answer) =>
    setAnswers((rows) => rows.map((a) => (a.id === updated.id ? updated : a)));

  const onRemove = (id: number) =>
    setAnswers((rows) => rows.filter((a) => a.id !== id));

  const submit = async () => {
    const q = question.trim();
    const a = answerText.trim();
    if (!q || !a) return;
    setAdding(true);
    const created = await api.createAnswer({
      question: q,
      answer: a,
      category: category.trim() || null,
    });
    setAdding(false);
    if (created) {
      setAnswers((rows) => [created, ...rows]);
      setQuestion("");
      setAnswerText("");
      setCategory("");
      flash("Answer added.");
    }
  };

  return (
    <div>
      <div className="phead">
        <div>
          <h1>Library answers</h1>
          <p className="sub">The questions you answer once and reuse across applications. Kept in your words, never invented.</p>
        </div>
      </div>

      <section className="card" style={{ padding: "18px 20px", marginBottom: 18 }}>
        <div className="sec-h" style={{ marginBottom: 14 }}>
          <span className="t">Add answer</span>
        </div>

        <label className="fld">
          <span className="fld__l">Question</span>
          <input
            className="inp"
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="Why do you want to work here?"
          />
        </label>

        <label className="fld" style={{ marginTop: 14 }}>
          <span className="fld__l">Answer</span>
          <textarea
            className="inp"
            value={answerText}
            onChange={(e) => setAnswerText(e.target.value)}
            placeholder="In your own words…"
            rows={4}
            style={{ resize: "vertical", fontFamily: "inherit" }}
          />
        </label>

        <label className="fld" style={{ marginTop: 14 }}>
          <span className="fld__l">Category (optional)</span>
          <input
            className="inp"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            placeholder="e.g. motivation, logistics, comp"
          />
        </label>

        <div style={{ marginTop: 16 }}>
          <button
            className="btn primary"
            disabled={adding || !question.trim() || !answerText.trim()}
            onClick={() => void submit()}
          >
            <Icon name="plus" size={14} /> Add answer
          </button>
        </div>
      </section>

      {loading ? (
        <div className="sub" style={{ padding: 20 }}>Loading…</div>
      ) : answers.length === 0 ? (
        <div className="card" style={{ padding: "28px 20px", textAlign: "center" }}>
          <span className="ic" style={{ width: 36, height: 36, borderRadius: 9, background: "var(--muted)", color: "var(--muted-foreground)", display: "inline-flex", alignItems: "center", justifyContent: "center", marginBottom: 10 }}>
            <Icon name="book-open" size={18} />
          </span>
          <p className="sub" style={{ margin: 0 }}>
            No answers yet. Add ones you reuse across applications, or ingest them with your library.
          </p>
        </div>
      ) : (
        <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
          {answers.map((a) => (
            <AnswerRow key={a.id} answer={a} flash={flash} onChange={onChange} onRemove={onRemove} />
          ))}
        </div>
      )}
    </div>
  );
}
