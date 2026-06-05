/* Matchbox — Studio app shell. Hosts the seven new surfaces, the ambient
   assistant, the profile switcher, and cross-links to Discover + Track. */
const { useState: useStApp, useEffect: useStFx, useRef: useStRef, useCallback: useStCb } = React;

const NAV = [
  { grp: "You" },
  { id: "intake", label: "Profile", icon: "user-round" },
  { id: "library", label: "Library", icon: "library" },
  { id: "sources", label: "Sources", icon: "radar" },
  { grp: "Apply" },
  { id: "tailoring", label: "Ready to apply", icon: "sparkles", badge: "1" },
  { id: "workspace", label: "Workspace", icon: "briefcase" },
  { grp: "Decide" },
  { id: "offers", label: "Offers", icon: "scale", badge: "•" },
  { id: "insights", label: "Insights", icon: "chart-line" },
  { grp: "Find & track" },
  { id: "discover", label: "Discover", icon: "compass", href: "Discovery.html" },
  { id: "track", label: "Applications", icon: "layout-list", href: "Matchbox.html" },
];

function StudioApp() {
  const S = window.STUDIO;
  const [nav, setNav] = useStApp("tailoring");
  const [profileId, setProfileId] = useStApp(S.profiles.find((p) => p.active).id);
  const [queue, setQueue] = useStApp(() => S.assistant.map((a) => ({ ...a })));
  const [trayOpen, setTrayOpen] = useStApp(false);
  const [toast, setToast] = useStApp(null);

  const flash = useStCb((msg, opts) => {
    setToast({ msg, ...(opts || {}) });
    clearTimeout(window.__st);
    window.__st = setTimeout(() => setToast(null), opts && opts.arrival ? 4500 : 2400);
  }, []);

  // Ambient assistant: the queued task starts after a beat, the working task
  // finishes after a beat — surfaced as calm arrivals, never a blocking spinner.
  useStFx(() => {
    const t1 = setTimeout(() => {
      setQueue((q) => q.map((it) => it.id === "a1" ? { ...it, state: "done", at: "just now" } : it));
      flash("Your tailored CV for Vercel is ready", { arrival: true, go: () => setNav("tailoring") });
    }, 6500);
    const t2 = setTimeout(() => {
      setQueue((q) => q.map((it) => it.id === "a2" ? { ...it, state: "working", eta: "under a minute" } : it));
    }, 3200);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, []);

  const profile = S.profiles.find((p) => p.id === profileId) || S.profiles[0];

  let screen;
  switch (nav) {
    case "intake": screen = <window.Intake data={S.intake} gaps={S.gaps} completeness={S.completeness} flash={flash} />; break;
    case "library": screen = <window.Library facts={S.facts} flash={flash} />; break;
    case "sources": screen = <window.Sources sources={S.searchSources} prefs={S.searchPrefs} flash={flash} />; break;
    case "workspace": screen = <window.Workspace data={S.workspace} flash={flash} />; break;
    case "offers": screen = <window.Offers data={S.offers} flash={flash} />; break;
    case "insights": screen = <window.StudioInsights data={S.insights} />; break;
    default: screen = <window.Tailoring data={S.tailoring} facts={S.facts} flash={flash} onApply={() => {}} />;
  }

  return (
    <div className="shell">
      <aside className="side">
        <div className="side__brand">
          <span className="mk"><span className="head" /><span className="stick" /></span>
          <b>Matchbox</b>
        </div>
        <nav className="side__nav" style={{ flex: "0 0 auto" }}>
          {NAV.map((it, i) => it.grp
            ? <div className="side__sec" key={"g" + i}>{it.grp}</div>
            : (
              <button key={it.id} className={window.scx("nav", nav === it.id && "active")}
                onClick={() => it.href ? (window.location.href = it.href) : setNav(it.id)}>
                <Icon name={it.icon} size={18} />
                <span>{it.label}</span>
                {it.badge && !it.href && <span className="ndot mono" style={{ marginLeft: "auto" }}>{it.badge}</span>}
                {it.href && <Icon name="arrow-up-right" size={14} style={{ marginLeft: "auto", color: "var(--faint-foreground)" }} />}
              </button>
            )
          )}
        </nav>

        {/* ambient assistant lives in the chrome, always visible, never blocking */}
        <div style={{ marginTop: "auto" }}>
          <window.AssistantChip queue={queue} onOpen={() => setTrayOpen((v) => !v)} />
          <div className="side__foot" style={{ marginTop: 8 }}>
            <window.ProfileSwitcher profiles={S.profiles} activeId={profileId} onSwitch={setProfileId} flash={flash} />
          </div>
        </div>
      </aside>

      <div className="main">
        <div className="pad" style={{ maxWidth: 1080 }}>{screen}</div>
      </div>

      {trayOpen && <window.ActivityTray queue={queue} onClose={() => setTrayOpen(false)} onGo={(it) => { setTrayOpen(false); setNav("tailoring"); }} />}

      {toast && (
        <div className="toasts">
          <div className={window.scx("toast", toast.arrival && "arrival")}>
            {toast.arrival ? <span className="ic"><Icon name="sparkles" size={15} /></span> : <Icon name="check-circle" size={16} />}
            {toast.msg}
            {toast.go && <button className="undo" onClick={() => { toast.go(); setToast(null); }}>Review</button>}
          </div>
        </div>
      )}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<StudioApp />);
