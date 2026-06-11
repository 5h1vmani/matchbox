/* Matchbox — Library. The verified store of your raw facts: experiences and
   their bullets, standalone projects, skills, and summary variants. This is the
   one place a model is ever allowed to pull from, and only after you confirm a
   fact here. Nothing on this screen is invented or computed — it edits rows.
   Verification is binary (a fact is yours or it is still a draft), metrics are
   honest (a chip only shows when the bullet carries a real number), and tags are
   the slim taxonomy the matcher reads: role_family, tech, seniority, impact. */
import { useEffect, useState } from "react";
import * as api from "../api/library";
import { cx } from "../lib/derive";
import { Icon } from "../ui/icon";

const FACETS = ["role_family", "tech", "seniority", "impact"] as const;
const PROFICIENCIES = ["working", "fluent", "expert"] as const;

function dateRange(start: string | null, end: string | null): string | null {
  if (!start && !end) return null;
  const tail = end ?? "Present";
  return start ? `${start} – ${tail}` : tail;
}

/* Tag chips ------------------------------------------------------------------- */

function TagChips({
  tags,
  itemType,
  itemId,
  flash,
  onTags,
}: {
  tags: api.Tag[];
  itemType: api.TagItemType;
  itemId: number;
  flash: (msg: string) => void;
  onTags: (tags: api.Tag[]) => void;
}) {
  const [adding, setAdding] = useState(false);
  const [facet, setFacet] = useState<string>(FACETS[0]);
  const [value, setValue] = useState("");
  const [busy, setBusy] = useState(false);

  const detach = async (tagId: number): Promise<void> => {
    setBusy(true);
    const ok = await api.deleteTag(itemType, itemId, tagId);
    setBusy(false);
    if (ok) {
      onTags(tags.filter((t) => t.id !== tagId));
      flash("Tag removed.");
    }
  };

  const attach = async (): Promise<void> => {
    const v = value.trim();
    if (!v) return;
    setBusy(true);
    const created = await api.addTag(itemType, itemId, { facet, value: v });
    setBusy(false);
    if (created) {
      onTags([...tags, created]);
      setValue("");
      setAdding(false);
      flash("Tag added.");
    } else {
      flash("Could not add that tag.");
    }
  };

  return (
    <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
      {tags.map((t) => (
        <span key={t.id} className="badge muted" style={{ display: "inline-flex", alignItems: "center", gap: 5 }}>
          <Icon name="tag" size={11} />
          <span className="mono">{t.facet}</span>:{t.value}
          <button
            className="btn ghost tiny"
            disabled={busy}
            style={{ padding: 0, minWidth: 0, marginLeft: 2 }}
            onClick={() => void detach(t.id)}
            aria-label="Remove tag"
            title="Remove tag"
          >
            <Icon name="x" size={11} />
          </button>
        </span>
      ))}

      {adding ? (
        <span style={{ display: "inline-flex", alignItems: "center", gap: 6, flexWrap: "wrap" }}>
          <select className="inp" value={facet} onChange={(e) => setFacet(e.target.value)} style={{ width: "auto" }}>
            {FACETS.map((f) => (
              <option key={f} value={f}>{f}</option>
            ))}
          </select>
          <input
            className="inp"
            value={value}
            onChange={(e) => setValue(e.target.value)}
            placeholder="value"
            style={{ width: 140 }}
            onKeyDown={(e) => { if (e.key === "Enter") void attach(); }}
          />
          <button className="btn tiny" disabled={busy || !value.trim()} onClick={() => void attach()}>
            <Icon name="check" size={12} /> Add
          </button>
          <button className="btn ghost tiny" disabled={busy} onClick={() => { setAdding(false); setValue(""); }}>
            <Icon name="x" size={12} /> Cancel
          </button>
        </span>
      ) : (
        <button className="btn ghost tiny" onClick={() => setAdding(true)}>
          <Icon name="tag" size={12} /> Add tag
        </button>
      )}
    </div>
  );
}

/* Bullets --------------------------------------------------------------------- */

function BulletRow({
  bullet,
  flash,
  onChange,
  onRemove,
}: {
  bullet: api.Bullet;
  flash: (msg: string) => void;
  onChange: (b: api.Bullet) => void;
  onRemove: (id: number) => void;
}) {
  const [busy, setBusy] = useState(false);

  const toggleVerified = async (): Promise<void> => {
    setBusy(true);
    const next = !bullet.verified;
    const updated = await api.patchBullet(bullet.id, { facts_verified: next });
    setBusy(false);
    if (updated) {
      onChange(updated);
      flash(next ? "Verified." : "Marked unverified.");
    }
  };

  const remove = async (): Promise<void> => {
    setBusy(true);
    const ok = await api.deleteBullet(bullet.id);
    setBusy(false);
    if (ok) {
      onRemove(bullet.id);
      flash("Bullet removed.");
    }
  };

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 8, marginTop: 14 }}>
      <p style={{ fontSize: 14, lineHeight: 1.5, margin: 0, whiteSpace: "pre-wrap" }}>{bullet.text}</p>
      <div style={{ display: "flex", alignItems: "center", gap: 10, flexWrap: "wrap" }}>
        <span className={cx("badge", bullet.verified ? "ok" : "muted")}>
          {bullet.verified ? "Verified" : "Unverified"}
        </span>
        {bullet.hasMetric && <span className="badge muted">metric</span>}
        <div style={{ display: "flex", gap: 8, marginLeft: "auto" }}>
          <button className="btn ghost tiny" disabled={busy} onClick={() => void toggleVerified()}>
            <Icon name={bullet.verified ? "x" : "check-circle"} size={13} />
            {bullet.verified ? " Mark unverified" : " Verify"}
          </button>
          <button className="btn ghost tiny" disabled={busy} onClick={() => void remove()}>
            <Icon name="trash-2" size={13} /> ×
          </button>
        </div>
      </div>
      <TagChips
        tags={bullet.tags}
        itemType="bullet"
        itemId={bullet.id}
        flash={flash}
        onTags={(tags) => onChange({ ...bullet, tags })}
      />
    </div>
  );
}

function AddBullet({
  experienceId,
  flash,
  onAdd,
}: {
  experienceId: number;
  flash: (msg: string) => void;
  onAdd: (b: api.Bullet) => void;
}) {
  const [text, setText] = useState("");
  const [hasMetric, setHasMetric] = useState(false);
  const [busy, setBusy] = useState(false);

  const submit = async (): Promise<void> => {
    const t = text.trim();
    if (!t) return;
    setBusy(true);
    const created = await api.addBullet({ experience_id: experienceId, text: t, has_metric: hasMetric });
    setBusy(false);
    if (created) {
      onAdd(created);
      setText("");
      setHasMetric(false);
      flash("Bullet added.");
    }
  };

  return (
    <div className="fld" style={{ marginTop: 16 }}>
      <span className="fld__l">Add bullet</span>
      <textarea
        className="inp"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="One fact, exactly as it happened…"
        rows={2}
        style={{ resize: "vertical", fontFamily: "inherit" }}
      />
      <div style={{ display: "flex", alignItems: "center", gap: 12, marginTop: 8, flexWrap: "wrap" }}>
        <label className="sub" style={{ display: "inline-flex", alignItems: "center", gap: 6, cursor: "pointer" }}>
          <input type="checkbox" checked={hasMetric} onChange={(e) => setHasMetric(e.target.checked)} />
          Carries a metric
        </label>
        <button className="btn tiny" disabled={busy || !text.trim()} onClick={() => void submit()}>
          <Icon name="plus" size={13} /> Add bullet
        </button>
      </div>
    </div>
  );
}

/* Experiences ----------------------------------------------------------------- */

function ExperienceCard({
  experience,
  flash,
  onBullet,
  onAddBullet,
  onRemoveBullet,
  onRemove,
}: {
  experience: api.Experience;
  flash: (msg: string) => void;
  onBullet: (b: api.Bullet) => void;
  onAddBullet: (b: api.Bullet) => void;
  onRemoveBullet: (id: number) => void;
  onRemove: (id: number) => void;
}) {
  const [busy, setBusy] = useState(false);
  const dates = dateRange(experience.startDate, experience.endDate);

  const remove = async (): Promise<void> => {
    if (!window.confirm("Delete this experience and all its bullets?")) return;
    setBusy(true);
    const ok = await api.deleteExperience(experience.id);
    setBusy(false);
    if (ok) {
      onRemove(experience.id);
      flash("Experience removed.");
    }
  };

  return (
    <div className="card" style={{ padding: "16px 20px" }}>
      <div className="sec-h" style={{ marginBottom: 6, alignItems: "flex-start" }}>
        <span className="t" style={{ flex: 1, minWidth: 0 }}>
          {experience.company}: {experience.role}
        </span>
        <button className="btn ghost tiny" disabled={busy} onClick={() => void remove()} title="Delete experience">
          <Icon name="trash-2" size={13} /> ×
        </button>
      </div>
      {(dates || experience.location) && (
        <p className="sub mono" style={{ margin: "0 0 4px" }}>
          {[dates, experience.location].filter(Boolean).join(" · ")}
        </p>
      )}

      {experience.bullets.length === 0 ? (
        <p className="sub" style={{ margin: "10px 0 0" }}>No bullets in this role yet. Add one below.</p>
      ) : (
        experience.bullets.map((b) => (
          <BulletRow key={b.id} bullet={b} flash={flash} onChange={onBullet} onRemove={onRemoveBullet} />
        ))
      )}

      <AddBullet experienceId={experience.id} flash={flash} onAdd={onAddBullet} />
    </div>
  );
}

function AddExperience({
  flash,
  onAdd,
}: {
  flash: (msg: string) => void;
  onAdd: (e: api.Experience) => void;
}) {
  const [company, setCompany] = useState("");
  const [role, setRole] = useState("");
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const [location, setLocation] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (): Promise<void> => {
    const c = company.trim();
    const r = role.trim();
    if (!c || !r) return;
    setBusy(true);
    const created = await api.addExperience({
      company: c,
      role: r,
      start_date: startDate.trim() || undefined,
      end_date: endDate.trim() || undefined,
      location: location.trim() || undefined,
    });
    setBusy(false);
    if (created) {
      onAdd(created);
      setCompany("");
      setRole("");
      setStartDate("");
      setEndDate("");
      setLocation("");
      flash("Experience added.");
    }
  };

  return (
    <section className="card" style={{ padding: "18px 20px", marginBottom: 18 }}>
      <div className="sec-h" style={{ marginBottom: 14 }}>
        <span className="t">Add experience</span>
      </div>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap" }}>
        <label className="fld" style={{ flex: "1 1 200px" }}>
          <span className="fld__l">Company</span>
          <input className="inp" value={company} onChange={(e) => setCompany(e.target.value)} placeholder="Acme Inc." />
        </label>
        <label className="fld" style={{ flex: "1 1 200px" }}>
          <span className="fld__l">Role</span>
          <input className="inp" value={role} onChange={(e) => setRole(e.target.value)} placeholder="Senior Engineer" />
        </label>
      </div>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", marginTop: 14 }}>
        <label className="fld" style={{ flex: "1 1 140px" }}>
          <span className="fld__l">Start (optional)</span>
          <input className="inp" value={startDate} onChange={(e) => setStartDate(e.target.value)} placeholder="2021" />
        </label>
        <label className="fld" style={{ flex: "1 1 140px" }}>
          <span className="fld__l">End (optional)</span>
          <input className="inp" value={endDate} onChange={(e) => setEndDate(e.target.value)} placeholder="Present" />
        </label>
        <label className="fld" style={{ flex: "1 1 200px" }}>
          <span className="fld__l">Location (optional)</span>
          <input className="inp" value={location} onChange={(e) => setLocation(e.target.value)} placeholder="Remote" />
        </label>
      </div>
      <div style={{ marginTop: 16 }}>
        <button className="btn primary" disabled={busy || !company.trim() || !role.trim()} onClick={() => void submit()}>
          <Icon name="plus" size={14} /> Add experience
        </button>
      </div>
    </section>
  );
}

/* Projects -------------------------------------------------------------------- */

function ProjectRow({
  project,
  flash,
  onTags,
  onRemove,
}: {
  project: api.Project;
  flash: (msg: string) => void;
  onTags: (tags: api.Tag[]) => void;
  onRemove: (id: number) => void;
}) {
  const [busy, setBusy] = useState(false);

  const remove = async (): Promise<void> => {
    setBusy(true);
    const ok = await api.deleteProject(project.id);
    setBusy(false);
    if (ok) {
      onRemove(project.id);
      flash("Project removed.");
    }
  };

  return (
    <div className="card" style={{ padding: "16px 20px" }}>
      <div className="sec-h" style={{ marginBottom: 8, alignItems: "flex-start" }}>
        <span className="t" style={{ flex: 1, minWidth: 0 }}>{project.name}</span>
        <span className={cx("badge", project.verified ? "ok" : "muted")} style={{ flex: "0 0 auto" }}>
          {project.verified ? "Verified" : "Unverified"}
        </span>
        <button className="btn ghost tiny" disabled={busy} onClick={() => void remove()} title="Delete project">
          <Icon name="trash-2" size={13} /> ×
        </button>
      </div>
      <p style={{ fontSize: 14, lineHeight: 1.5, margin: "0 0 10px", whiteSpace: "pre-wrap" }}>{project.text}</p>
      {project.url && (
        <a className="sub mono" href={project.url} target="_blank" rel="noreferrer" style={{ display: "inline-block", marginBottom: 10 }}>
          {project.url}
        </a>
      )}
      <TagChips tags={project.tags} itemType="project" itemId={project.id} flash={flash} onTags={onTags} />
    </div>
  );
}

function AddProject({
  flash,
  onAdd,
}: {
  flash: (msg: string) => void;
  onAdd: (p: api.Project) => void;
}) {
  const [name, setName] = useState("");
  const [text, setText] = useState("");
  const [url, setUrl] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (): Promise<void> => {
    const n = name.trim();
    const t = text.trim();
    if (!n || !t) return;
    setBusy(true);
    const created = await api.addProject({ name: n, text: t, url: url.trim() || undefined });
    setBusy(false);
    if (created) {
      onAdd(created);
      setName("");
      setText("");
      setUrl("");
      flash("Project added.");
    }
  };

  return (
    <div className="card" style={{ padding: "18px 20px" }}>
      <div className="sec-h" style={{ marginBottom: 14 }}>
        <span className="t">Add project</span>
      </div>
      <label className="fld">
        <span className="fld__l">Name</span>
        <input className="inp" value={name} onChange={(e) => setName(e.target.value)} placeholder="Open-source tool" />
      </label>
      <label className="fld" style={{ marginTop: 14 }}>
        <span className="fld__l">Description</span>
        <textarea
          className="inp"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="What it is and what you did…"
          rows={3}
          style={{ resize: "vertical", fontFamily: "inherit" }}
        />
      </label>
      <label className="fld" style={{ marginTop: 14 }}>
        <span className="fld__l">URL (optional)</span>
        <input className="inp" value={url} onChange={(e) => setUrl(e.target.value)} placeholder="https://github.com/…" />
      </label>
      <div style={{ marginTop: 16 }}>
        <button className="btn primary" disabled={busy || !name.trim() || !text.trim()} onClick={() => void submit()}>
          <Icon name="plus" size={14} /> Add project
        </button>
      </div>
    </div>
  );
}

/* Skills ---------------------------------------------------------------------- */

function AddSkill({
  flash,
  onAdd,
}: {
  flash: (msg: string) => void;
  onAdd: (s: api.Skill) => void;
}) {
  const [name, setName] = useState("");
  const [category, setCategory] = useState("");
  const [proficiency, setProficiency] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (): Promise<void> => {
    const n = name.trim();
    if (!n) return;
    setBusy(true);
    const result = await api.addSkill({
      name: n,
      category: category.trim() || undefined,
      proficiency: proficiency || undefined,
    });
    setBusy(false);
    if (result.duplicate) {
      flash("That skill is already in your library.");
      return;
    }
    if (result.skill) {
      onAdd(result.skill);
      setName("");
      setCategory("");
      setProficiency("");
      flash("Skill added.");
    }
  };

  return (
    <div className="card" style={{ padding: "18px 20px", marginBottom: 14 }}>
      <div className="sec-h" style={{ marginBottom: 14 }}>
        <span className="t">Add skill</span>
      </div>
      <div style={{ display: "flex", gap: 12, flexWrap: "wrap", alignItems: "flex-end" }}>
        <label className="fld" style={{ flex: "1 1 200px" }}>
          <span className="fld__l">Name</span>
          <input className="inp" value={name} onChange={(e) => setName(e.target.value)} placeholder="Kubernetes" />
        </label>
        <label className="fld" style={{ flex: "1 1 160px" }}>
          <span className="fld__l">Category (optional)</span>
          <input className="inp" value={category} onChange={(e) => setCategory(e.target.value)} placeholder="Infrastructure" />
        </label>
        <label className="fld" style={{ flex: "1 1 140px" }}>
          <span className="fld__l">Proficiency (optional)</span>
          <select className="inp" value={proficiency} onChange={(e) => setProficiency(e.target.value)}>
            <option value="">(none)</option>
            {PROFICIENCIES.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>
        </label>
      </div>
      <div style={{ marginTop: 16 }}>
        <button className="btn primary" disabled={busy || !name.trim()} onClick={() => void submit()}>
          <Icon name="plus" size={14} /> Add skill
        </button>
      </div>
    </div>
  );
}

function SkillRow({
  skill,
  flash,
  onRemove,
}: {
  skill: api.Skill;
  flash: (msg: string) => void;
  onRemove: (id: number) => void;
}) {
  const [busy, setBusy] = useState(false);

  const remove = async (): Promise<void> => {
    setBusy(true);
    const ok = await api.deleteSkill(skill.id);
    setBusy(false);
    if (ok) {
      onRemove(skill.id);
      flash("Skill removed.");
    }
  };

  return (
    <span className="badge muted" style={{ display: "inline-flex", alignItems: "center", gap: 6 }}>
      {skill.name}
      {skill.category && <span className="sub">· {skill.category}</span>}
      {skill.proficiency && <span className="mono">· {skill.proficiency}</span>}
      <button
        className="btn ghost tiny"
        disabled={busy}
        style={{ padding: 0, minWidth: 0, marginLeft: 2 }}
        onClick={() => void remove()}
        aria-label="Remove skill"
        title="Remove skill"
      >
        <Icon name="x" size={11} />
      </button>
    </span>
  );
}

/* Summaries ------------------------------------------------------------------- */

function AddSummary({
  flash,
  onAdd,
}: {
  flash: (msg: string) => void;
  onAdd: (s: api.Summary) => void;
}) {
  const [label, setLabel] = useState("");
  const [text, setText] = useState("");
  const [busy, setBusy] = useState(false);

  const submit = async (): Promise<void> => {
    const l = label.trim();
    const t = text.trim();
    if (!l || !t) return;
    setBusy(true);
    const created = await api.addSummary({ label: l, text: t });
    setBusy(false);
    if (created) {
      onAdd(created);
      setLabel("");
      setText("");
      flash("Summary added.");
    }
  };

  return (
    <div className="card" style={{ padding: "18px 20px", marginBottom: 14 }}>
      <div className="sec-h" style={{ marginBottom: 14 }}>
        <span className="t">Add summary</span>
      </div>
      <label className="fld">
        <span className="fld__l">Label</span>
        <input className="inp" value={label} onChange={(e) => setLabel(e.target.value)} placeholder="Platform-leaning" />
      </label>
      <label className="fld" style={{ marginTop: 14 }}>
        <span className="fld__l">Text</span>
        <textarea
          className="inp"
          value={text}
          onChange={(e) => setText(e.target.value)}
          placeholder="A positioning paragraph in your own words…"
          rows={3}
          style={{ resize: "vertical", fontFamily: "inherit" }}
        />
      </label>
      <div style={{ marginTop: 16 }}>
        <button className="btn primary" disabled={busy || !label.trim() || !text.trim()} onClick={() => void submit()}>
          <Icon name="plus" size={14} /> Add summary
        </button>
      </div>
    </div>
  );
}

function SummaryRow({
  summary,
  flash,
  onRemove,
}: {
  summary: api.Summary;
  flash: (msg: string) => void;
  onRemove: (id: number) => void;
}) {
  const [busy, setBusy] = useState(false);

  const remove = async (): Promise<void> => {
    setBusy(true);
    const ok = await api.deleteSummary(summary.id);
    setBusy(false);
    if (ok) {
      onRemove(summary.id);
      flash("Summary removed.");
    }
  };

  return (
    <div className="card" style={{ padding: "16px 20px" }}>
      <div className="sec-h" style={{ marginBottom: 8, alignItems: "flex-start" }}>
        <span className="t" style={{ flex: 1, minWidth: 0 }}>{summary.label}</span>
        <button className="btn ghost tiny" disabled={busy} onClick={() => void remove()} title="Delete summary">
          <Icon name="trash-2" size={13} /> ×
        </button>
      </div>
      <p style={{ fontSize: 14, lineHeight: 1.5, margin: 0, whiteSpace: "pre-wrap" }}>{summary.text}</p>
    </div>
  );
}

/* Screen ---------------------------------------------------------------------- */

export function Library({ flash }: { flash: (msg: string) => void }) {
  const [state, setState] = useState<api.LibraryState | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    void api.getLibrary().then((s) => {
      setState(s);
      setLoading(false);
    });
  }, []);

  /* Experience mutations ------------------------------------------------------ */
  const addExperience = (e: api.Experience): void =>
    setState((s) => (s ? { ...s, experiences: [{ ...e, bullets: e.bullets ?? [] }, ...s.experiences] } : s));

  const removeExperience = (id: number): void =>
    setState((s) => (s ? { ...s, experiences: s.experiences.filter((e) => e.id !== id) } : s));

  const addBulletTo = (b: api.Bullet): void =>
    setState((s) =>
      s
        ? {
            ...s,
            experiences: s.experiences.map((e) =>
              e.id === b.experienceId ? { ...e, bullets: [...e.bullets, b] } : e,
            ),
          }
        : s,
    );

  const changeBullet = (b: api.Bullet): void =>
    setState((s) =>
      s
        ? {
            ...s,
            experiences: s.experiences.map((e) =>
              e.id === b.experienceId
                ? { ...e, bullets: e.bullets.map((x) => (x.id === b.id ? b : x)) }
                : e,
            ),
          }
        : s,
    );

  const removeBullet = (id: number): void =>
    setState((s) =>
      s
        ? {
            ...s,
            experiences: s.experiences.map((e) => ({
              ...e,
              bullets: e.bullets.filter((x) => x.id !== id),
            })),
          }
        : s,
    );

  /* Project mutations --------------------------------------------------------- */
  const addProject = (p: api.Project): void =>
    setState((s) => (s ? { ...s, projects: [p, ...s.projects] } : s));

  const removeProject = (id: number): void =>
    setState((s) => (s ? { ...s, projects: s.projects.filter((p) => p.id !== id) } : s));

  const setProjectTags = (id: number, tags: api.Tag[]): void =>
    setState((s) =>
      s ? { ...s, projects: s.projects.map((p) => (p.id === id ? { ...p, tags } : p)) } : s,
    );

  /* Skill mutations ----------------------------------------------------------- */
  const addSkill = (sk: api.Skill): void =>
    setState((s) => (s ? { ...s, skills: [...s.skills, sk] } : s));

  const removeSkill = (id: number): void =>
    setState((s) => (s ? { ...s, skills: s.skills.filter((sk) => sk.id !== id) } : s));

  /* Summary mutations --------------------------------------------------------- */
  const addSummary = (su: api.Summary): void =>
    setState((s) => (s ? { ...s, summaries: [su, ...s.summaries] } : s));

  const removeSummary = (id: number): void =>
    setState((s) => (s ? { ...s, summaries: s.summaries.filter((su) => su.id !== id) } : s));

  if (loading || !state) {
    return (
      <div>
        <div className="phead">
          <div>
            <h1>Library</h1>
            <p className="sub">Your verified facts. A model only ever pulls from what lives here.</p>
          </div>
        </div>
        <div className="sub" style={{ padding: 20 }}>Loading…</div>
      </div>
    );
  }

  return (
    <div>
      <div className="phead">
        <div>
          <h1>Library</h1>
          <p className="sub">
            Your verified facts: experiences, projects, skills, and summaries. A model only ever
            pulls from what lives here, and nothing here is invented.
          </p>
        </div>
      </div>

      {/* Experience */}
      <section style={{ marginBottom: 26 }}>
        <div className="sec-h" style={{ marginBottom: 12 }}>
          <span className="t">Experience</span>
        </div>
        <AddExperience flash={flash} onAdd={addExperience} />
        {state.experiences.length === 0 ? (
          <div className="card" style={{ padding: "24px 20px", textAlign: "center" }}>
            <p className="sub" style={{ margin: 0 }}>No experience yet. Add a role above, then give it bullets.</p>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {state.experiences.map((e) => (
              <ExperienceCard
                key={e.id}
                experience={e}
                flash={flash}
                onBullet={changeBullet}
                onAddBullet={addBulletTo}
                onRemoveBullet={removeBullet}
                onRemove={removeExperience}
              />
            ))}
          </div>
        )}
      </section>

      {/* Projects */}
      <section style={{ marginBottom: 26 }}>
        <div className="sec-h" style={{ marginBottom: 12 }}>
          <span className="t">Projects</span>
        </div>
        <div style={{ marginBottom: 14 }}>
          <AddProject flash={flash} onAdd={addProject} />
        </div>
        {state.projects.length === 0 ? (
          <div className="card" style={{ padding: "24px 20px", textAlign: "center" }}>
            <p className="sub" style={{ margin: 0 }}>No projects yet. Add standalone work like open-source or side projects.</p>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {state.projects.map((p) => (
              <ProjectRow
                key={p.id}
                project={p}
                flash={flash}
                onTags={(tags) => setProjectTags(p.id, tags)}
                onRemove={removeProject}
              />
            ))}
          </div>
        )}
      </section>

      {/* Skills */}
      <section style={{ marginBottom: 26 }}>
        <div className="sec-h" style={{ marginBottom: 12 }}>
          <span className="t">Skills</span>
        </div>
        <AddSkill flash={flash} onAdd={addSkill} />
        {state.skills.length === 0 ? (
          <div className="card" style={{ padding: "24px 20px", textAlign: "center" }}>
            <p className="sub" style={{ margin: 0 }}>No skills yet. Add the ones you would put on a CV.</p>
          </div>
        ) : (
          <div className="card" style={{ padding: "16px 20px" }}>
            <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
              {state.skills.map((sk) => (
                <SkillRow key={sk.id} skill={sk} flash={flash} onRemove={removeSkill} />
              ))}
            </div>
          </div>
        )}
      </section>

      {/* Summaries */}
      <section style={{ marginBottom: 26 }}>
        <div className="sec-h" style={{ marginBottom: 12 }}>
          <span className="t">Summaries</span>
        </div>
        <AddSummary flash={flash} onAdd={addSummary} />
        {state.summaries.length === 0 ? (
          <div className="card" style={{ padding: "24px 20px", textAlign: "center" }}>
            <p className="sub" style={{ margin: 0 }}>No summary variants yet. Add positioning paragraphs you reuse.</p>
          </div>
        ) : (
          <div style={{ display: "flex", flexDirection: "column", gap: 14 }}>
            {state.summaries.map((su) => (
              <SummaryRow key={su.id} summary={su} flash={flash} onRemove={removeSummary} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
