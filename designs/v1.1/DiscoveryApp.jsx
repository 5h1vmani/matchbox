/* Matchbox — Discovery app shell. Sidebar + routing + decisions + toast + tweaks.
   Cross-links to the tracker (Matchbox.html). */
const { useState: useDAppState, useMemo: useDAppMemo, useCallback: useDCb } = React;

const D_DEFAULTS = /*EDITMODE-BEGIN*/{
  "density": "regular",
  "accent": "taupe"
}/*EDITMODE-END*/;

const D_ACCENTS = {
  taupe:  { "--oat-600": "#574747", "--oat-700": "#473a3a", "--oat-100": "#ede8e8", "--oat-300": "#b6a6a6" },
  forest: { "--oat-600": "#2f6b46", "--oat-700": "#265739", "--oat-100": "#e3efe7", "--oat-300": "#a9c8b4" },
  slate:  { "--oat-600": "#2f5d72", "--oat-700": "#264c5e", "--oat-100": "#e2ecf1", "--oat-300": "#a6c0cc" },
};

const DECISION_TOAST = {
  tracked: "Tracked. It's in your applications.",
  tailoring: "Sent to tailor. Drafting your CV now.",
  dismissed: "Dismissed. You won't see it again.",
  watch: "Added the company to your watchlist.",
  skip: "Skipped. We'll bring it back tomorrow.",
};

function DSidebar({ nav, onNav, queueCount }) {
  const item = (id, label, icon, opts = {}) => (
    <button className={window.dcx("nav", nav === id && "active")} onClick={() => onNav(id, opts.href)}>
      <Icon name={icon} size={18} />
      <span>{label}</span>
      {opts.badge != null && opts.badge > 0 && <span className="ndot mono">{opts.badge}</span>}
      {opts.ext && <Icon name="arrow-up-right" size={14} style={{ marginLeft: "auto", color: "var(--faint-foreground)" }} />}
    </button>
  );
  return (
    <aside className="side">
      <div className="side__brand">
        <span className="mk"><span className="head" /><span className="stick" /></span>
        <b>Matchbox</b>
      </div>
      <nav className="side__nav">
        <div className="side__sec" style={{ paddingTop: 8 }}>Discover</div>
        {item("review", "Today's roles", "sparkles", { badge: queueCount })}
        {item("browse", "Browse", "search")}
        {item("watchlist", "Watchlist", "bookmark")}
        <div className="side__sec">Track</div>
        {item("today", "Today", "sun", { href: "Matchbox.html", ext: true })}
        {item("applications", "Applications", "layout-list", { href: "Matchbox.html", ext: true })}
        {item("insights", "Insights", "chart-line", { href: "Matchbox.html", ext: true })}
      </nav>
      <div className="side__foot">
        <div className="userchip">
          <span className="av">JS</span>
          <div>
            <div className="nm">Job seeker</div>
            <div className="sub"><span className="live" /> Saved locally</div>
          </div>
        </div>
      </div>
    </aside>
  );
}

function DiscoveryApp() {
  const [roles, setRoles] = useDAppState(() => window.ROLES.map((r) => ({ ...r })));
  const [watch, setWatch] = useDAppState(() => window.WATCH.map((w) => ({ ...w })));
  const [t, setTweak] = useTweaks(D_DEFAULTS);
  const [nav, setNav] = useDAppState("review");
  const [jd, setJd] = useDAppState(null); // role id
  const [sel, setSel] = useDAppState(() => new Set());
  const [toast, setToast] = useDAppState(null);

  React.useEffect(() => {
    const root = document.documentElement;
    const set = D_ACCENTS[t.accent] || D_ACCENTS.taupe;
    Object.entries(set).forEach(([k, v]) => root.style.setProperty(k, v));
  }, [t.accent]);

  const flash = useDCb((msg, undo) => {
    setToast({ msg, undo });
    clearTimeout(window.__dt);
    window.__dt = setTimeout(() => setToast(null), undo ? 4200 : 2400);
  }, []);

  const applyDecision = useDCb((ids, decision) => {
    const prev = {};
    setRoles((list) => list.map((r) => {
      if (ids.includes(r.id)) { prev[r.id] = r.decision; return { ...r, decision: decision === "skip" ? r.decision : decision === "watch" ? "dismissed" : decision }; }
      return r;
    }));
    if (decision === "watch") {
      setRoles((list) => {
        const role = list.find((r) => ids.includes(r.id));
        if (role) setWatch((w) => w.find((x) => x.company === role.company) ? w : [{ company: role.company, note: "Watching for a role you're eligible for.", status: "watching", openRoles: 0, mono: role.mono }, ...w]);
        return list;
      });
    }
    return prev;
  }, []);

  const undoDecision = useDCb((prev) => {
    setRoles((list) => list.map((r) => (r.id in prev ? { ...r, decision: prev[r.id] } : r)));
  }, []);

  const onDecide = useDCb((role, decision) => {
    const prev = applyDecision([role.id], decision);
    flash(DECISION_TOAST[decision] || "Done", () => undoDecision(prev));
  }, [applyDecision, flash, undoDecision]);

  const toggleSel = useDCb((id) => {
    setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  }, []);
  const clearSel = useDCb(() => setSel(new Set()), []);

  const onBatch = useDCb((decision) => {
    const ids = [...sel];
    const prev = applyDecision(ids, decision);
    clearSel();
    const verb = decision === "tailoring" ? "Sent " + ids.length + " to tailor." : decision === "tracked" ? "Tracked " + ids.length + " roles." : "Dismissed " + ids.length + ".";
    flash(verb, () => undoDecision(prev));
  }, [sel, applyDecision, clearSel, flash, undoDecision]);

  const onNav = useDCb((id, href) => {
    if (href) { window.location.href = href; return; }
    setNav(id);
  }, []);

  const queueCount = useDAppMemo(() =>
    roles.filter((r) => !r.decision && r.eligibility.status !== "ineligible" && r.freshness !== "closed").length,
  [roles]);

  const jdRole = useDAppMemo(() => jd && roles.find((r) => r.id === jd), [jd, roles]);

  let screen;
  if (nav === "browse") screen = <window.Browse roles={roles} sel={sel} onToggleSel={toggleSel} onClearSel={clearSel} onOpen={(r) => setJd(r.id)} onDecide={onDecide} onBatch={onBatch} flash={flash} />;
  else if (nav === "watchlist") screen = <window.Watchlist watch={watch} flash={flash} />;
  else screen = <window.Review roles={roles} onDecide={onDecide} onOpenJD={(r) => setJd(r.id)} onGoBrowse={() => setNav("browse")} flash={flash} />;

  return (
    <div className="shell" data-density={t.density}>
      <DSidebar nav={nav} onNav={onNav} queueCount={queueCount} />
      <div className="main">
        <div className="pad">{screen}</div>
      </div>

      {jdRole && <window.JDDrawer role={jdRole} onDecide={onDecide} onClose={() => setJd(null)} flash={flash} />}

      {toast && (
        <div className="toasts">
          <div className="toast">
            <Icon name="check-circle" size={16} /> {toast.msg}
            {toast.undo && <button className="undo" onClick={() => { toast.undo(); setToast(null); }}>Undo</button>}
          </div>
        </div>
      )}

      <TweaksPanel>
        <TweakSection label="Feel" />
        <TweakRadio label="Density" value={t.density}
          options={[{ value: "regular", label: "Regular" }, { value: "compact", label: "Compact" }]}
          onChange={(v) => setTweak("density", v)} />
        <TweakRadio label="Accent" value={t.accent}
          options={[{ value: "taupe", label: "Taupe" }, { value: "forest", label: "Forest" }, { value: "slate", label: "Slate" }]}
          onChange={(v) => setTweak("accent", v)} />
        <p style={{ fontSize: 12, color: "var(--muted-foreground)", margin: "4px 0 0", lineHeight: 1.45 }}>
          Discovery shares the tracker's shell and tokens. Use the sidebar's Track section to jump to the applications side.
        </p>
      </TweaksPanel>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<DiscoveryApp />);
