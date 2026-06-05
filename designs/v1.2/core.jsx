/* Matchbox — unified core atoms. Merges the former ui/dui/sui modules into one
   shared module so the whole app runs under a single React root with no global
   collisions. Every screen references these (bare or via window.*). */
const { useEffect: useCFx, useRef: useCRef, useState: useCSt } = React;

function cx() { return Array.prototype.slice.call(arguments).filter(Boolean).join(" "); }

/* Lucide icon wrapper. */
function Icon({ name, size = 18, style, className, strokeWidth = 2 }) {
  const ref = useCRef(null);
  useCFx(() => {
    if (ref.current && window.lucide) {
      ref.current.innerHTML = "";
      const el = document.createElement("i");
      el.setAttribute("data-lucide", name);
      ref.current.appendChild(el);
      window.lucide.createIcons({ attrs: { width: size, height: size, "stroke-width": strokeWidth }, nameAttr: "data-lucide" });
    }
  }, [name, size, strokeWidth]);
  return <span ref={ref} className={className} style={{ display: "inline-flex", lineHeight: 0, ...style }} />;
}

/* Unified monogram: accepts an `app` (tracker) or `role` (discovery). */
function MonoLogo({ app, role, size = 34, radius = 8 }) {
  const src = app || role;
  const initials = src.company.replace(/[^A-Za-z0-9]/g, "").slice(0, 2);
  return (
    <span className="mono-logo" style={{ background: src.mono.bg, color: src.mono.fg, width: size, height: size, borderRadius: radius, fontSize: Math.round(size * 0.4) }}>
      {initials.charAt(0).toUpperCase() + (initials.charAt(1) || "").toLowerCase()}
    </span>
  );
}

/* Studio monogram: takes m + label directly. */
function Mono({ m, label, size = 38, radius = 9 }) {
  const initials = label.replace(/[^A-Za-z0-9]/g, "").slice(0, 2);
  return (
    <span className="mono-logo" style={{ background: m.bg, color: m.fg, width: size, height: size, borderRadius: radius, fontSize: Math.round(size * 0.4) }}>
      {initials.charAt(0).toUpperCase() + (initials.charAt(1) || "").toLowerCase()}
    </span>
  );
}

/* ---- tracker stage helpers ---- */
function stageMeta(id) { return window.STAGES.find((x) => x.id === id) || { id, label: id, tone: "#a1a1aa" }; }
function stageLabel(id) { return stageMeta(id).label; }
function stageIndex(id) { return window.STAGES.findIndex((x) => x.id === id); }
function StageDot({ stage, size = 8 }) { return <span className="sdot" style={{ width: size, height: size, background: stageMeta(stage).tone }} />; }

function dueInfo(due) {
  if (due === null || due === undefined) return null;
  if (due < 0) return { cls: "over", text: (-due) + "d overdue", short: (-due) + "d late", icon: "alert-circle" };
  if (due === 0) return { cls: "today", text: "Today", short: "Today", icon: "circle-dot" };
  if (due === 1) return { cls: "soon", text: "Tomorrow", short: "Tmrw", icon: "clock-3" };
  if (due <= 6) return { cls: "soon", text: "in " + due + " days", short: due + "d", icon: "clock-3" };
  return { cls: "later", text: "in " + due + " days", short: due + "d", icon: "clock-3" };
}
function Due({ due, short }) {
  const info = dueInfo(due);
  if (!info) return null;
  return <span className={"due " + info.cls}><Icon name={info.icon} size={11} /> {short ? info.short : info.text}</span>;
}
function updatedText(days) { if (days <= 0) return "today"; if (days === 1) return "yesterday"; return days + "d ago"; }
function appliedText(days) {
  if (days === null || days === undefined) return "Not applied";
  if (days === 0) return "Applied today";
  if (days === 1) return "Applied yesterday";
  return "Applied " + days + "d ago";
}
function actionPhrase(app) {
  const a = app.nextAction;
  if (!a) return { lead: "No action needed", sub: null, plain: true };
  switch (a.kind) {
    case "interview": return { lead: a.label, strong: app.company, joiner: " with ", sub: app.role + (a.time ? " · " + a.time : "") };
    case "offer": return { lead: "Respond to " + app.company, sub: app.role + " · " + app.salary, offer: true };
    case "apply": return { lead: "Apply to", strong: app.company, sub: app.role };
    case "followup": return { lead: "Follow up with", strong: app.company, sub: app.role };
    case "prep": return { lead: "Prep for", strong: app.company, sub: app.role };
    case "thanks": return { lead: "Send thank-you to", strong: app.company, sub: app.role };
    case "wait": return { lead: "Waiting to hear back", sub: app.company + " · " + app.role, plain: true };
    default: return { lead: a.label, sub: app.role };
  }
}
function ActionLine({ app }) {
  const p = actionPhrase(app);
  return <span>{p.lead}{p.joiner ? p.joiner : (p.strong ? " " : "")}{p.strong && <b>{p.strong}</b>}</span>;
}
function Badge({ tone = "neutral", children, dot }) {
  return <span className={cx("mbadge", "t-" + tone, dot && "has-dot")}>{children}</span>;
}
function StageStepper({ stage }) {
  const flow = window.STAGES.filter((s) => s.id !== "rejected");
  const closed = stage === "rejected";
  const curIdx = closed ? -1 : flow.findIndex((s) => s.id === stage);
  return (
    <div className={cx("stepper", closed && "is-closed")}>
      {flow.map((s, i) => {
        const done = !closed && i < curIdx;
        const cur = !closed && i === curIdx;
        return (
          <div key={s.id} className={cx("step", done && "done", cur && "cur")}>
            <span className="step__dot" style={cur ? { background: s.tone, borderColor: s.tone } : null}>{done && <Icon name="check" size={11} />}</span>
            <span className="step__lbl">{s.short}</span>
          </div>
        );
      })}
    </div>
  );
}
function eventIcon(kind) {
  return { saved: "bookmark", applied: "send", reply: "mail", screen: "phone", onsite: "users", offer: "party-popper", rejected: "x-circle", note: "sticky-note", followup: "reply", advanced: "arrow-right", thanks: "heart" }[kind] || "circle";
}

/* ---- discovery reads ---- */
const FIT_META = {
  strong:  { dots: 4, label: "Strong fit", tone: "#2f6b46", bg: "#e7f5ec" },
  good:    { dots: 3, label: "Good fit", tone: "#574747", bg: "#ede8e8" },
  stretch: { dots: 2, label: "A stretch", tone: "#8a5a1f", bg: "#f5ead9" },
};
function FitMeter({ fit, compact }) {
  const meta = FIT_META[fit.level] || FIT_META.good;
  return (
    <div className={cx("read", "fit", compact && "compact")}>
      <div className="read__head">
        <span className="dots" aria-hidden="true">{[0, 1, 2, 3].map((i) => <span key={i} className="dot" style={{ background: i < meta.dots ? meta.tone : "var(--zinc-200)" }} />)}</span>
        <span className="read__label" style={{ color: meta.tone }}>{meta.label}</span>
      </div>
      {!compact && <p className="read__reason">{fit.reason}</p>}
    </div>
  );
}
const ELIG_META = {
  eligible: { icon: "check", label: "Eligible to apply", tone: "#2f6b46" },
  unclear: { icon: "help-circle", label: "Worth checking", tone: "#8a5a1f" },
  ineligible: { icon: "minus-circle", label: "Likely not eligible", tone: "var(--muted-foreground)" },
};
function EligibilityRead({ elig, compact }) {
  const meta = ELIG_META[elig.status] || ELIG_META.eligible;
  return (
    <div className={cx("read", "elig", "is-" + elig.status, compact && "compact")}>
      <div className="read__head">
        <span className="read__ic" style={{ color: meta.tone }}><Icon name={meta.icon} size={compact ? 14 : 16} /></span>
        <span className="read__label" style={{ color: meta.tone }}>{meta.label}</span>
      </div>
      {!compact && <p className="read__reason">{elig.reason}</p>}
    </div>
  );
}
function Freshness({ role, plain }) {
  if (role.freshness === "closed") return <span className="fresh closed"><Icon name="lock" size={11} /> Closed</span>;
  if (role.freshness === "closing") return <span className="fresh closing"><Icon name="clock-3" size={11} /> {"Closing in " + role.closingInDays + " days"}</span>;
  const p = role.postedDaysAgo;
  const txt = p <= 0 ? "Posted today" : p === 1 ? "Posted yesterday" : "Posted " + p + " days ago";
  if (plain) return <span className="fresh open plain"><Icon name="circle" size={9} /> {txt}</span>;
  return <span className="fresh open">{txt}</span>;
}
function Coverage({ coverage, compact }) {
  if (!coverage) return null;
  const pct = Math.round((coverage.covered / coverage.total) * 100);
  return (
    <div className={cx("cov", compact && "compact")}>
      <div className="cov__top">
        <span className="cov__lbl">CV covers {coverage.covered} of {coverage.total} must-haves</span>
        {!compact && <span className="cov__pct mono">{pct}%</span>}
      </div>
      <div className="cov__track"><div className="cov__fill" style={{ width: pct + "%" }} /></div>
    </div>
  );
}
function fullLoc(role) {
  if (role.remote) { const where = role.location.replace(/remote/i, "").replace(/[()]/g, "").trim(); return "Remote" + (where ? " · " + where : ""); }
  return role.location;
}

/* ---- cross-cutting A: provenance ---- */
function Provenance({ children }) { return <span className="prov"><Icon name="link" size={11} /> {children}</span>; }

/* ---- cross-cutting B: confidence ---- */
const CONF_LABEL = { low: "Low confidence", medium: "Some confidence", high: "Solid" };
function Confidence({ level }) {
  return <span className={cx("conf", level)} title={CONF_LABEL[level]}><span className="conf__dots"><i /><i /><i /></span>{CONF_LABEL[level] || level}</span>;
}
function Estimate({ value, range, level, basis }) {
  return (
    <div className={cx("estimate", level)}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <span className="estimate__val">{value}</span>
        <Confidence level={level} />
      </div>
      {range && <div className="estimate__range">{range}</div>}
      {basis && <div className="estimate__basis"><Icon name="info" size={14} /> <span>{basis}</span></div>}
    </div>
  );
}

/* ---- cross-cutting C: ambient assistant ---- */
function assistantSummary(queue) {
  const working = queue.filter((q) => q.state === "working");
  const queued = queue.filter((q) => q.state === "queued");
  const active = working.length + queued.length;
  if (working.length) return { state: "working", title: working.length === 1 ? working[0].label : "Assistant is working", sub: working[0].eta ? working[0].eta + (active > 1 ? " · " + (active - 1) + " more queued" : "") : (active - 1) + " more queued", count: active };
  if (queued.length) return { state: "working", title: "Queued", sub: queued.length + " task" + (queued.length > 1 ? "s" : "") + " waiting", count: queued.length };
  return { state: "idle", title: "Assistant is ready", sub: "Nothing running. Hand it some work.", count: 0 };
}
function AssistantChip({ queue, onOpen }) {
  const s = assistantSummary(queue);
  return (
    <div className="assistant-chip" onClick={onOpen} title="Open assistant activity">
      <div className="assistant-chip__row">
        <span className={cx("assistant-chip__dot", s.state)} />
        <div style={{ minWidth: 0 }}>
          <div className="assistant-chip__t">{s.title}</div>
          <div className="assistant-chip__s">{s.sub}</div>
        </div>
        {s.count > 0 && <span className="assistant-chip__n">{s.count}</span>}
      </div>
    </div>
  );
}
const TRAY_ICON = { tailor: "sparkles", draft: "pen-line", prep: "clipboard-list" };
function ActivityTray({ queue, onClose, onGo }) {
  const ref = useCRef(null);
  useCFx(() => {
    function h(e) { if (ref.current && !ref.current.contains(e.target) && !e.target.closest(".assistant-chip")) onClose(); }
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  const order = { working: 0, queued: 1, done: 2 };
  const sorted = [...queue].sort((a, b) => order[a.state] - order[b.state]);
  return (
    <div className="tray" ref={ref}>
      <div className="tray__h">
        <Icon name="sparkles" size={15} style={{ color: "var(--oat-600)" }} />
        <span className="t">Assistant activity</span>
        <span className="sp" />
        <span style={{ fontSize: 11.5, color: "var(--muted-foreground)" }}>on this device</span>
      </div>
      <div className="tray__body">
        {sorted.map((it) => (
          <div className="trayitem" key={it.id}>
            <span className={cx("trayitem__ic", it.state)}><Icon name={TRAY_ICON[it.kind] || "sparkles"} size={15} /></span>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div className="trayitem__t">{it.label}</div>
              <div className="trayitem__s">
                {it.state === "working" && <React.Fragment><span className="spin" /> working · {it.eta}</React.Fragment>}
                {it.state === "queued" && "queued"}
                {it.state === "done" && <React.Fragment><Icon name="check" size={11} style={{ color: "var(--success)" }} /> ready · {it.at}</React.Fragment>}
              </div>
            </div>
            {it.state === "done" && onGo && <button className="btn ghost tiny go" onClick={() => onGo(it)}>Review</button>}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ---- profile switcher ---- */
function ProfileSwitcher({ profiles, activeId, onSwitch, flash }) {
  const [open, setOpen] = useCSt(false);
  const ref = useCRef(null);
  useCFx(() => {
    function h(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false); }
    document.addEventListener("mousedown", h);
    return () => document.removeEventListener("mousedown", h);
  }, []);
  const active = profiles.find((p) => p.id === activeId) || profiles[0];
  return (
    <div className="pswitch" ref={ref}>
      {open && (
        <div className="pswitch__menu">
          <div className="localnote"><Icon name="hard-drive" size={12} /> On this device. Nothing syncs.</div>
          {profiles.map((p) => (
            <div className="pswitch__item" key={p.id} onClick={() => { onSwitch(p.id); setOpen(false); flash && flash("Switched to " + p.name); }}>
              <span className="pswitch__av" style={{ background: p.color }}>{p.initials}</span>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div className="pswitch__nm">{p.name}</div>
                <div className="pswitch__fl">{p.file}</div>
              </div>
              {p.id === active.id && <span className="check"><Icon name="check" size={16} /></span>}
            </div>
          ))}
          <div className="pswitch__div" />
          <div className="pswitch__add" onClick={() => { setOpen(false); flash && flash("Would create a new local profile"); }}>
            <span className="pswitch__av" style={{ background: "var(--muted)", color: "var(--muted-foreground)" }}><Icon name="plus" size={15} /></span>
            Add another person
          </div>
        </div>
      )}
      <div className="userchip" onClick={() => setOpen((v) => !v)}>
        <span className="av" style={{ background: active.color, color: "#fff" }}>{active.initials}</span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="nm">{active.name}</div>
          <div className="sub"><span className="live" /> Saved locally</div>
        </div>
        <Icon name="chevrons-up-down" size={15} style={{ color: "var(--faint-foreground)" }} />
      </div>
    </div>
  );
}

window.cx = cx; window.dcx = cx; window.scx = cx;
Object.assign(window, {
  Icon, MonoLogo, Mono, StageDot, Due, dueInfo, updatedText, appliedText,
  stageMeta, stageLabel, stageIndex, actionPhrase, ActionLine, Badge, StageStepper, eventIcon,
  FitMeter, EligibilityRead, Freshness, Coverage, FIT_META, ELIG_META, fullLoc,
  Provenance, Confidence, Estimate, assistantSummary, AssistantChip, ActivityTray, ProfileSwitcher,
});
