/* Matchbox — Review (the v0.3 honesty guardrail). A model pulls facts out of
   your files; this screen makes it confirm them before they count. Verification
   is binary — a fact is either yours or it is still a draft, never a percentage
   and never a trust score. Everything here renders what the server measured;
   nothing is invented, nothing is auto-trusted. */
import { useEffect, useState } from "react";
import * as api from "../api/review";
import { cx } from "../lib/derive";
import { Icon } from "../ui/icon";

function dateRange(start: string | null, end: string | null): string | null {
  if (!start && !end) return null;
  const tail = end ?? "Present";
  return start ? `${start} – ${tail}` : tail;
}

function VerifiedPill({ verified }: { verified: boolean }) {
  return (
    <span className={cx("badge", verified ? "ok" : "muted")}>
      {verified ? "Verified" : "Unverified"}
    </span>
  );
}

function BulletRow({
  bullet,
  flash,
  onChange,
  onRemove,
}: {
  bullet: api.ReviewBullet;
  flash: (msg: string) => void;
  onChange: (b: api.ReviewBullet) => void;
  onRemove: (id: number) => void;
}) {
  const [editing, setEditing] = useState(false);
  const [draft, setDraft] = useState(bullet.text);
  const [busy, setBusy] = useState(false);

  const toggleVerified = async () => {
    setBusy(true);
    const next = !bullet.verified;
    const updated = next ? await api.verifyBullet(bullet.id) : await api.unverifyBullet(bullet.id);
    setBusy(false);
    if (updated) {
      onChange(updated);
      flash(next ? "Verified." : "Marked unverified.");
    }
  };

  const saveEdit = async () => {
    const text = draft.trim();
    if (!text || text === bullet.text) {
      setEditing(false);
      setDraft(bullet.text);
      return;
    }
    setBusy(true);
    const updated = await api.editBullet(bullet.id, { text });
    setBusy(false);
    if (updated) {
      onChange(updated);
      setEditing(false);
      flash("Bullet updated.");
    }
  };

  const remove = async () => {
    setBusy(true);
    const ok = await api.deleteBullet(bullet.id);
    setBusy(false);
    if (ok) {
      onRemove(bullet.id);
      flash("Bullet removed.");
    }
  };

  if (editing) {
    return (
      <div className="fld" style={{ marginTop: 12 }}>
        <span className="fld__l">Bullet</span>
        <textarea
          className="inp"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={3}
          style={{ resize: "vertical", fontFamily: "inherit" }}
        />
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <button className="btn tiny" disabled={busy} onClick={() => void saveEdit()}>
            <Icon name="check" size={13} /> Save
          </button>
          <button
            className="btn ghost tiny"
            disabled={busy}
            onClick={() => { setEditing(false); setDraft(bullet.text); }}
          >
            <Icon name="x" size={13} /> Cancel
          </button>
        </div>
      </div>
    );
  }

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 12 }}>
      <p style={{ fontSize: 14, lineHeight: 1.5, margin: 0, whiteSpace: "pre-wrap" }}>{bullet.text}</p>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <VerifiedPill verified={bullet.verified} />
        {bullet.hasMetric && <span className="badge muted">metric</span>}
        {bullet.sourceFile && (
          <span className="sub" style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
            <Icon name="book-open" size={13} /> {bullet.sourceFile}
          </span>
        )}
        <div style={{ display: "flex", gap: 8, marginLeft: "auto" }}>
          <button className="btn ghost tiny" disabled={busy} onClick={() => void toggleVerified()}>
            <Icon name={bullet.verified ? "x" : "check-circle"} size={13} />
            {bullet.verified ? " Mark unverified" : " Verify"}
          </button>
          <button
            className="btn ghost tiny"
            disabled={busy}
            onClick={() => { setDraft(bullet.text); setEditing(true); }}
          >
            <Icon name="edit-3" size={13} /> Edit
          </button>
          <button className="btn ghost tiny" disabled={busy} onClick={() => void remove()}>
            <Icon name="trash-2" size={13} /> ×
          </button>
        </div>
      </div>
    </div>
  );
}

function ExperienceCard({
  experience,
  flash,
  onBullet,
  onRemoveBullet,
  onVerifyAll,
}: {
  experience: api.ReviewExperience;
  flash: (msg: string) => void;
  onBullet: (b: api.ReviewBullet) => void;
  onRemoveBullet: (id: number) => void;
  onVerifyAll: (result: api.VerifyExperienceResult) => void;
}) {
  const [busy, setBusy] = useState(false);
  const dates = dateRange(experience.startDate, experience.endDate);

  const verifyRole = async () => {
    setBusy(true);
    const result = await api.verifyExperience(experience.id);
    setBusy(false);
    if (result) {
      onVerifyAll(result);
      flash("Verified all bullets in this role.");
    }
  };

  return (
    <div className="card" style={{ padding: "16px 20px" }}>
      <div className="sec-h" style={{ marginBottom: 6, alignItems: "flex-start" }}>
        <span className="t" style={{ flex: 1, minWidth: 0 }}>
          {experience.company}: {experience.role}
        </span>
        <button className="btn ghost tiny" disabled={busy} onClick={() => void verifyRole()}>
          <Icon name="check-circle" size={13} /> Verify all in this role
        </button>
      </div>
      {dates && <p className="sub mono" style={{ margin: "0 0 4px" }}>{dates}</p>}

      {experience.bullets.length === 0 ? (
        <p className="sub" style={{ margin: "10px 0 0" }}>No bullets pulled from this role yet.</p>
      ) : (
        experience.bullets.map((b) => (
          <BulletRow
            key={b.id}
            bullet={b}
            flash={flash}
            onChange={onBullet}
            onRemove={onRemoveBullet}
          />
        ))
      )}
    </div>
  );
}

function ProjectCard({
  project,
  flash,
  onChange,
}: {
  project: api.ReviewProject;
  flash: (msg: string) => void;
  onChange: (p: api.ReviewProject) => void;
}) {
  const [busy, setBusy] = useState(false);

  const verify = async () => {
    if (project.verified) return;
    setBusy(true);
    const updated = await api.verifyProject(project.id);
    setBusy(false);
    if (updated) {
      onChange(updated);
      flash("Verified.");
    }
  };

  return (
    <div className="card" style={{ padding: "16px 20px" }}>
      <div className="sec-h" style={{ marginBottom: 8, alignItems: "flex-start" }}>
        <span className="t" style={{ flex: 1, minWidth: 0 }}>{project.name}</span>
        <VerifiedPill verified={project.verified} />
      </div>
      <p style={{ fontSize: 14, lineHeight: 1.5, margin: "0 0 10px", whiteSpace: "pre-wrap" }}>{project.text}</p>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        {project.url && (
          <a className="sub mono" href={project.url} target="_blank" rel="noreferrer">{project.url}</a>
        )}
        {!project.verified && (
          <button className="btn ghost tiny" disabled={busy} style={{ marginLeft: "auto" }} onClick={() => void verify()}>
            <Icon name="check-circle" size={13} /> Verify
          </button>
        )}
      </div>
    </div>
  );
}

function AnswerCard({
  answer,
  flash,
  onChange,
}: {
  answer: api.ReviewAnswer;
  flash: (msg: string) => void;
  onChange: (a: api.ReviewAnswer) => void;
}) {
  const [busy, setBusy] = useState(false);

  const verify = async () => {
    if (answer.verified) return;
    setBusy(true);
    const updated = await api.verifyAnswer(answer.id);
    setBusy(false);
    if (updated) {
      onChange(updated);
      flash("Verified.");
    }
  };

  return (
    <div className="card" style={{ padding: "16px 20px" }}>
      <div className="sec-h" style={{ marginBottom: 8, alignItems: "flex-start" }}>
        <span className="t" style={{ flex: 1, minWidth: 0 }}>{answer.question}</span>
        <VerifiedPill verified={answer.verified} />
      </div>
      <p style={{ fontSize: 14, lineHeight: 1.5, margin: "0 0 10px", whiteSpace: "pre-wrap" }}>{answer.answer}</p>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        {answer.category && <span className="badge muted">{answer.category}</span>}
        <span className="sub">used <span className="mono">{answer.usedCount}</span> time{answer.usedCount === 1 ? "" : "s"}</span>
        {answer.sourceFile && (
          <span className="sub" style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
            <Icon name="book-open" size={13} /> {answer.sourceFile}
          </span>
        )}
        {!answer.verified && (
          <button className="btn ghost tiny" disabled={busy} style={{ marginLeft: "auto" }} onClick={() => void verify()}>
            <Icon name="check-circle" size={13} /> Verify
          </button>
        )}
      </div>
    </div>
  );
}

export function ReviewFacts({ flash }: { flash: (msg: string) => void }) {
  const [state, setState] = useState<api.ReviewState | null>(null);
  const [loading, setLoading] = useState(true);
  const [verifyingAll, setVerifyingAll] = useState(false);

  useEffect(() => {
    void api.getReview().then((s) => {
      setState(s);
      setLoading(false);
    });
  }, []);

  const onBullet = (updated: api.ReviewBullet) =>
    setState((s) =>
      s
        ? {
            ...s,
            experiences: s.experiences.map((e) =>
              e.id === updated.experienceId
                ? { ...e, bullets: e.bullets.map((b) => (b.id === updated.id ? updated : b)) }
                : e,
            ),
          }
        : s,
    );

  const onRemoveBullet = (id: number) =>
    setState((s) =>
      s
        ? {
            ...s,
            experiences: s.experiences.map((e) => ({
              ...e,
              bullets: e.bullets.filter((b) => b.id !== id),
            })),
          }
        : s,
    );

  const onVerifyExperience = (result: api.VerifyExperienceResult) =>
    setState((s) =>
      s
        ? {
            ...s,
            experiences: s.experiences.map((e) =>
              e.id === result.experienceId ? { ...e, bullets: result.bullets } : e,
            ),
          }
        : s,
    );

  const onProject = (updated: api.ReviewProject) =>
    setState((s) =>
      s ? { ...s, projects: s.projects.map((p) => (p.id === updated.id ? updated : p)) } : s,
    );

  const onAnswer = (updated: api.ReviewAnswer) =>
    setState((s) =>
      s ? { ...s, answers: s.answers.map((a) => (a.id === updated.id ? updated : a)) } : s,
    );

  const verifyEverything = async () => {
    if (!window.confirm("Mark every fact as verified? You vouch for all of it.")) return;
    setVerifyingAll(true);
    const next = await api.verifyAll();
    setVerifyingAll(false);
    setState(next);
    flash("Everything verified.");
  };

  if (loading) {
    return (
      <div>
        <div className="phead">
          <div>
            <h1>Review</h1>
            <p className="sub">Confirm each fact a model pulled from your files. Nothing is used until you verify it.</p>
          </div>
        </div>
        <div className="sub" style={{ padding: 20 }}>Loading…</div>
      </div>
    );
  }

  const isEmpty =
    !state ||
    (state.experiences.length === 0 && state.projects.length === 0 && state.answers.length === 0);

  if (isEmpty) {
    return (
      <div>
        <div className="phead">
          <div>
            <h1>Review</h1>
            <p className="sub">Confirm each fact a model pulled from your files. Nothing is used until you verify it.</p>
          </div>
        </div>
        <div className="card" style={{ padding: "28px 20px", textAlign: "center" }}>
          <p className="sub" style={{ margin: 0 }}>Nothing to review yet. Ingest your files first.</p>
        </div>
      </div>
    );
  }

  const totalUnverified =
    state.unverifiedBullets + state.unverifiedProjects + state.unverifiedAnswers;

  return (
    <div>
      <div className="phead">
        <div>
          <h1>Review</h1>
          <p className="sub">Confirm each fact a model pulled from your files. Nothing is used until you verify it.</p>
        </div>
        {totalUnverified > 0 && (
          <button className="btn" disabled={verifyingAll} onClick={() => void verifyEverything()}>
            <Icon name="check-circle" size={14} /> Verify everything
          </button>
        )}
      </div>

      <p className="sub" style={{ marginBottom: 18 }}>
        {totalUnverified === 0 ? (
          "Every fact is verified. Nothing is waiting on you."
        ) : (
          <>
            Still unverified:{" "}
            <span className="mono">{state.unverifiedBullets}</span> bullet{state.unverifiedBullets === 1 ? "" : "s"},{" "}
            <span className="mono">{state.unverifiedProjects}</span> project{state.unverifiedProjects === 1 ? "" : "s"},{" "}
            <span className="mono">{state.unverifiedAnswers}</span> answer{state.unverifiedAnswers === 1 ? "" : "s"}.
          </>
        )}
      </p>

      {state.experiences.length > 0 && (
        <section style={{ marginBottom: 22 }}>
          <div className="sec-h" style={{ marginBottom: 12 }}>
            <span className="t">Experience</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {state.experiences.map((e) => (
              <ExperienceCard
                key={e.id}
                experience={e}
                flash={flash}
                onBullet={onBullet}
                onRemoveBullet={onRemoveBullet}
                onVerifyAll={onVerifyExperience}
              />
            ))}
          </div>
        </section>
      )}

      {state.projects.length > 0 && (
        <section style={{ marginBottom: 22 }}>
          <div className="sec-h" style={{ marginBottom: 12 }}>
            <span className="t">Projects</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {state.projects.map((p) => (
              <ProjectCard key={p.id} project={p} flash={flash} onChange={onProject} />
            ))}
          </div>
        </section>
      )}

      {state.answers.length > 0 && (
        <section style={{ marginBottom: 22 }}>
          <div className="sec-h" style={{ marginBottom: 12 }}>
            <span className="t">Answers</span>
          </div>
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {state.answers.map((a) => (
              <AnswerCard key={a.id} answer={a} flash={flash} onChange={onAnswer} />
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
