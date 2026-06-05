/* Matchbox — Studio shared atoms + the three cross-cutting components. */
const { useEffect: useSFx, useRef: useSRef, useState: useSSt } = React;

function scx() { return Array.prototype.slice.call(arguments).filter(Boolean).join(" "); }

function Icon({ name, size = 18, style, className, strokeWidth = 2 }) {
  const ref = useSRef(null);
  useSFx(() => {
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

function Mono({ m, label, size = 38, radius = 9 }) {
  const initials = label.replace(/[^A-Za-z0-9]/g, "").slice(0, 2);
  return (
    <span className="mono-logo" style={{ background: m.bg, color: m.fg, width: size, height: size, borderRadius: radius, fontSize: Math.round(size * 0.4), display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 600, flex: "0 0 auto" }}>
      {initials.charAt(0).toUpperCase() + (initials.charAt(1) || "").toLowerCase()}
    </span>
  );
}

/* ---- CROSS-CUTTING A: provenance chip ---- */
function Provenance({ children }) {
  return <span className="prov"><Icon name="link" size={11} /> {children}</span>;
}

/* ---- CROSS-CUTTING B: confidence affordance ---- */
const CONF_LABEL = { low: "Low confidence", medium: "Some confidence", high: "Solid" };
function Confidence({ level }) {
  return (
    <span className={scx("conf", level)} title={CONF_LABEL[level]}>
      <span className="conf__dots"><i /><i /><i /></span>
      {CONF_LABEL[level] || level}
    </span>
  );
}

/* An honest estimate: value + range + confidence + basis (never false precision). */
function Estimate({ value, range, level, basis }) {
  return (
    <div className={scx("estimate", level)}>
      <div style={{ display: "flex", alignItems: "center", gap: 12, flexWrap: "wrap" }}>
        <span className="estimate__val">{value}</span>
        <Confidence level={level} />
      </div>
      {range && <div className="estimate__range">{range}</div>}
      {basis && <div className="estimate__basis"><Icon name="info" size={14} /> <span>{basis}</span></div>}
    </div>
  );
}

/* ---- CROSS-CUTTING C: ambient assistant ---- */
function assistantSummary(queue) {
  const working = queue.filter((q) => q.state === "working");
  const queued = queue.filter((q) => q.state === "queued");
  const active = working.length + queued.length;
  if (working.length) {
    return { state: "working", title: working.length === 1 ? working[0].label : "Assistant is working", sub: working[0].eta ? working[0].eta + (active > 1 ? " · " + (active - 1) + " more queued" : "") : (active - 1) + " more queued", count: active };
  }
  if (queued.length) return { state: "working", title: "Queued", sub: queued.length + " task" + (queued.length > 1 ? "s" : "") + " waiting", count: queued.length };
  return { state: "idle", title: "Assistant is ready", sub: "Nothing running. Hand it some work.", count: 0 };
}

function AssistantChip({ queue, onOpen }) {
  const s = assistantSummary(queue);
  return (
    <div className="assistant-chip" onClick={onOpen} title="Open assistant activity">
      <div className="assistant-chip__row">
        <span className={scx("assistant-chip__dot", s.state)} />
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
  const ref = useSRef(null);
  useSFx(() => {
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
            <span className={scx("trayitem__ic", it.state)}><Icon name={TRAY_ICON[it.kind] || "sparkles"} size={15} /></span>
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
  const [open, setOpen] = useSSt(false);
  const ref = useSRef(null);
  useSFx(() => {
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

Object.assign(window, { scx, Icon, Mono, Provenance, Confidence, Estimate, AssistantChip, ActivityTray, ProfileSwitcher, assistantSummary });
