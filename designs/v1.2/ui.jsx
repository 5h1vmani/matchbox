/* Matchbox — shared atoms & helpers. Exposed on window. */
const { useEffect: useFx, useRef: useRefA, useState: useStateA } = React;

function cx() {
  return Array.prototype.slice.call(arguments).filter(Boolean).join(" ");
}

/* Lucide icon wrapper. Renders an inline SVG via the CDN lib. */
function Icon({ name, size = 18, style, className, strokeWidth = 2 }) {
  const ref = useRefA(null);
  useFx(() => {
    if (ref.current && window.lucide) {
      ref.current.innerHTML = "";
      const el = document.createElement("i");
      el.setAttribute("data-lucide", name);
      ref.current.appendChild(el);
      window.lucide.createIcons({
        attrs: { width: size, height: size, "stroke-width": strokeWidth },
        nameAttr: "data-lucide",
      });
    }
  }, [name, size, strokeWidth]);
  return <span ref={ref} className={className} style={{ display: "inline-flex", lineHeight: 0, ...style }} />;
}

function stageMeta(id) {
  return window.STAGES.find((x) => x.id === id) || { id, label: id, tone: "#a1a1aa" };
}
function stageLabel(id) { return stageMeta(id).label; }
function stageIndex(id) { return window.STAGES.findIndex((x) => x.id === id); }

/* Monogram logo from company initials. */
function MonoLogo({ app, size = 34, radius = 8 }) {
  const initials = app.company.replace(/[^A-Za-z0-9]/g, "").slice(0, 2);
  return (
    <span className="mono-logo" style={{
      background: app.mono.bg, color: app.mono.fg,
      width: size, height: size, borderRadius: radius,
      fontSize: Math.round(size * 0.4),
    }}>
      {initials.charAt(0).toUpperCase() + (initials.charAt(1) || "")}
    </span>
  );
}

function StageDot({ stage, size = 8 }) {
  return <span className="sdot" style={{ width: size, height: size, background: stageMeta(stage).tone }} />;
}

/* due: integer days from today (neg = overdue, 0 = today), or null. */
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
  return (
    <span className={"due " + info.cls}>
      <Icon name={info.icon} size={11} /> {short ? info.short : info.text}
    </span>
  );
}

function updatedText(days) {
  if (days <= 0) return "today";
  if (days === 1) return "yesterday";
  return days + "d ago";
}
function appliedText(days) {
  if (days === null || days === undefined) return "Not applied";
  if (days === 0) return "Applied today";
  if (days === 1) return "Applied yesterday";
  return "Applied " + days + "d ago";
}

/* Human verb for an action kind. */
function actionPhrase(app) {
  const a = app.nextAction;
  if (!a) return { lead: "No action needed", sub: null, plain: true };
  switch (a.kind) {
    case "interview":
      return { lead: a.label, strong: app.company, joiner: " with ", sub: app.role + (a.time ? " · " + a.time : "") };
    case "offer":
      return { lead: "Respond to " + app.company, sub: app.role + " · " + app.salary, offer: true };
    case "apply":
      return { lead: "Apply to", strong: app.company, sub: app.role };
    case "followup":
      return { lead: "Follow up with", strong: app.company, sub: app.role };
    case "prep":
      return { lead: "Prep for", strong: app.company, sub: app.role };
    case "thanks":
      return { lead: "Send thank-you to", strong: app.company, sub: app.role };
    case "wait":
      return { lead: "Waiting to hear back", sub: app.company + " · " + app.role, plain: true };
    default:
      return { lead: a.label, sub: app.role };
  }
}

/* Compose the action line as JSX. */
function ActionLine({ app }) {
  const p = actionPhrase(app);
  return (
    <span>
      {p.lead}
      {p.joiner ? p.joiner : (p.strong ? " " : "")}
      {p.strong && <b>{p.strong}</b>}
    </span>
  );
}

/* small status badge */
function Badge({ tone = "neutral", children, dot }) {
  return <span className={cx("mbadge", "t-" + tone, dot && "has-dot")}>{children}</span>;
}

/* Stage stepper for the detail view — shows pipeline progress honestly. */
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
            <span className="step__dot" style={cur ? { background: s.tone, borderColor: s.tone } : null}>
              {done && <Icon name="check" size={11} />}
            </span>
            <span className="step__lbl">{s.short}</span>
          </div>
        );
      })}
    </div>
  );
}

/* Icon for a timeline event kind. */
function eventIcon(kind) {
  return {
    saved: "bookmark", applied: "send", reply: "mail", screen: "phone",
    onsite: "users", offer: "party-popper", rejected: "x-circle",
    note: "sticky-note", followup: "reply", advanced: "arrow-right", thanks: "heart",
  }[kind] || "circle";
}

Object.assign(window, {
  cx, Icon, MonoLogo, StageDot, Due, dueInfo, updatedText, appliedText,
  stageMeta, stageLabel, stageIndex, actionPhrase, ActionLine, Badge,
  StageStepper, eventIcon,
});
