/* Matchbox — unified application shell. One sidebar, one router, one React root.
   Hosts every surface: discover, track, apply, decide, and the build/you tools.
   The ambient assistant and the profile switcher are global chrome. */
const { useState: useMSt, useMemo: useMMemo, useEffect: useMFx, useCallback: useMCb } = React;

const D_FLOW = ["saved", "applied", "phone", "onsite", "offer"];

const M_NAV = [
  { grp: "Discover" },
  { id: "review", label: "Review", icon: "sparkles", badge: "queue" },
  { id: "browse", label: "Browse roles", icon: "search" },
  { id: "watchlist", label: "Watchlist", icon: "bookmark" },
  { grp: "Track" },
  { id: "today", label: "Today", icon: "sun", dot: "todo" },
  { id: "applications", label: "Applications", icon: "layout-list", badge: "apps" },
  { grp: "Apply" },
  { id: "apply", label: "Ready to apply", icon: "wand-sparkles", badge: "static1" },
  { id: "workspace", label: "Workspace", icon: "briefcase" },
  { id: "people", label: "People", icon: "users-round" },
  { grp: "Decide" },
  { id: "offers", label: "Offers", icon: "scale", badge: "dot" },
  { id: "insights", label: "Insights", icon: "chart-line" },
  { grp: "You" },
  { id: "profile", label: "Profile", icon: "user-round" },
  { id: "library", label: "Library", icon: "library" },
  { id: "sources", label: "Sources", icon: "radar" },
  { id: "settings", label: "Settings", icon: "settings" },
];

const ROLE_TOAST = {
  tracked: "Tracked. It's in your applications.",
  tailoring: "Sent to tailor. Drafting your CV now.",
  dismissed: "Dismissed. You won't see it again.",
  watch: "Added the company to your watchlist.",
  skip: "Skipped. We'll bring it back tomorrow.",
};

function MatchboxApp() {
  const S = window.STUDIO;
  const A = window.APPLY;
  const [apps, appActions] = window.useApps();
  const [roles, setRoles] = useMSt(() => window.ROLES.map((r) => ({ ...r })));
  const [watch, setWatch] = useMSt(() => window.WATCH.map((w) => ({ ...w })));
  const [profiles] = useMSt(() => S.profiles.map((p) => ({ ...p })));
  const [profileId, setProfileId] = useMSt(S.profiles.find((p) => p.active).id);
  const [queue, setQueue] = useMSt(() => S.assistant.map((a) => ({ ...a })));

  const [route, setRoute] = useMSt("today");
  const [view, setView] = useMSt("list");
  const [filter, setFilter] = useMSt("all");
  const [sel, setSel] = useMSt(() => new Set());

  const [detail, setDetail] = useMSt(null);   // tracker app: { id, note }
  const [jd, setJd] = useMSt(null);           // discovery role id
  const [trayOpen, setTrayOpen] = useMSt(false);
  const [paletteOpen, setPaletteOpen] = useMSt(false);
  const [toast, setToast] = useMSt(null);

  const profile = profiles.find((p) => p.id === profileId) || profiles[0];

  const flash = useMCb((msg, opts) => {
    const t = { msg };
    if (typeof opts === "function") t.undo = opts;
    else if (opts) Object.assign(t, opts);
    setToast(t);
    clearTimeout(window.__mt);
    window.__mt = setTimeout(() => setToast(null), t.arrival ? 4500 : (t.undo ? 4000 : 2400));
  }, []);

  // ambient assistant progression — calm, never blocking
  useMFx(() => {
    const t2 = setTimeout(() => setQueue((q) => q.map((it) => it.id === "a2" ? { ...it, state: "working", eta: "under a minute" } : it)), 3400);
    const t1 = setTimeout(() => {
      setQueue((q) => q.map((it) => it.id === "a1" ? { ...it, state: "done", at: "just now" } : it));
      flash("Your tailored CV for Vercel is ready", { arrival: true, go: () => setRoute("apply") });
    }, 7000);
    return () => { clearTimeout(t1); clearTimeout(t2); };
  }, []);

  // ⌘K command palette
  useMFx(() => {
    const onKey = (e) => {
      if ((e.metaKey || e.ctrlKey) && (e.key === "k" || e.key === "K")) { e.preventDefault(); setPaletteOpen((v) => !v); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  // expose the assistant queue + active profile to the AI layer, so live
  // generations appear as ambient work and use this person's own key
  useMFx(() => { window.__mbProfile = profileId; }, [profileId]);
  useMFx(() => {
    window.MBQueue = {
      start: (label, kind) => {
        const id = "live-" + Date.now() + "-" + Math.random().toString(36).slice(2, 6);
        setQueue((q) => [{ id, label, kind: kind || "draft", state: "working", eta: "a few seconds" }, ...q]);
        return id;
      },
      done: (id) => setQueue((q) => q.map((it) => it.id === id ? { ...it, state: "done", at: "just now" } : it)),
    };
    return () => { window.MBQueue = null; };
  }, []);

  // ---- tracker overlays ----
  const openDetail = useMCb((app, mode) => setDetail({ id: app.id, note: mode === "note" }), []);
  const detailApp = useMMemo(() => detail && apps.find((a) => a.id === detail.id), [detail, apps]);

  // ---- discovery state ----
  const openJD = useMCb((role) => setJd(role.id), []);
  const jdRole = useMMemo(() => jd && roles.find((r) => r.id === jd), [jd, roles]);

  const commands = useMMemo(() => {
    const nav = (id, label, icon, hint) => ({ id: "nav-" + id, group: "Go to", label, icon, hint, run: () => setRoute(id) });
    return [
      nav("today", "Today", "sun", "What needs you now"),
      nav("review", "Review new roles", "sparkles", "Today's matches"),
      nav("browse", "Browse roles", "search"),
      nav("applications", "Applications", "layout-list", "Your pipeline"),
      nav("apply", "Ready to apply", "wand-sparkles", "The Linear packet"),
      nav("workspace", "Workspace", "briefcase", "Prep & interview loop"),
      nav("people", "People", "users-round", "Network & referrals"),
      nav("offers", "Offers", "scale"),
      nav("insights", "Insights", "chart-line"),
      nav("profile", "Profile", "user-round"),
      nav("library", "Library", "library", "Sentences & answers"),
      nav("sources", "Sources", "radar"),
      nav("settings", "Settings", "settings", "Bring your own key"),
      { id: "act-tailor", group: "Actions", label: "Tailor a CV for a role", icon: "wand-sparkles", run: () => setRoute("apply") },
      { id: "act-add", group: "Actions", label: "Add an application", icon: "plus", run: () => { setRoute("applications"); flash("New application form would open"); } },
      { id: "act-ask", group: "Actions", label: "Ask someone for a referral", icon: "git-pull-request-arrow", run: () => setRoute("people") },
      { id: "act-assist", group: "Actions", label: "Open assistant activity", icon: "sparkles", run: () => setTrayOpen(true) },
    ];
  }, [flash]);

  const applyDecision = useMCb((ids, decision) => {
    const prev = {};
    setRoles((list) => list.map((r) => {
      if (ids.includes(r.id)) { prev[r.id] = r.decision; return { ...r, decision: decision === "skip" ? r.decision : decision === "watch" ? "dismissed" : decision }; }
      return r;
    }));
    if (decision === "watch") {
      const role = roles.find((r) => ids.includes(r.id));
      if (role) setWatch((w) => w.find((x) => x.company === role.company) ? w : [{ company: role.company, note: "Watching for a role you're eligible for.", status: "watching", openRoles: 0, mono: role.mono }, ...w]);
    }
    if (decision === "tailoring") {
      const role = roles.find((r) => ids.includes(r.id));
      setQueue((q) => [{ id: "q" + Date.now(), label: "Tailoring CV for " + (role ? role.company : ids.length + " roles"), kind: "tailor", state: "working", eta: "under a minute" }, ...q]);
    }
    return prev;
  }, [roles]);

  const onRoleDecide = useMCb((role, decision) => {
    const prev = applyDecision([role.id], decision);
    flash(ROLE_TOAST[decision] || "Done", () => setRoles((list) => list.map((r) => (r.id in prev ? { ...r, decision: prev[r.id] } : r))));
  }, [applyDecision]);

  const toggleSel = useMCb((id) => setSel((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; }), []);
  const clearSel = useMCb(() => setSel(new Set()), []);
  const onBatch = useMCb((decision) => {
    const ids = [...sel];
    const prev = applyDecision(ids, decision);
    clearSel();
    const verb = decision === "tailoring" ? "Sent " + ids.length + " to tailor." : decision === "tracked" ? "Tracked " + ids.length + " roles." : "Dismissed " + ids.length + ".";
    flash(verb, () => setRoles((list) => list.map((r) => (r.id in prev ? { ...r, decision: prev[r.id] } : r))));
  }, [sel, applyDecision]);

  // ---- counts for sidebar ----
  const queueCount = useMMemo(() => roles.filter((r) => !r.decision && r.eligibility.status !== "ineligible" && r.freshness !== "closed").length, [roles]);
  const todoCount = useMMemo(() => apps.filter((a) => a.nextAction && a.nextAction.due !== null && a.nextAction.due <= 1 && a.stage !== "rejected" && a.nextAction.kind !== "wait").length, [apps]);
  const badgeVal = (b) => b === "queue" ? queueCount : b === "apps" ? apps.length : b === "static1" ? 1 : b === "dot" ? "•" : null;

  // ---- screen ----
  let screen;
  switch (route) {
    case "review": screen = <window.Review roles={roles} onDecide={onRoleDecide} onOpenJD={openJD} onGoBrowse={() => setRoute("browse")} flash={flash} />; break;
    case "browse": screen = <window.Browse roles={roles} sel={sel} onToggleSel={toggleSel} onClearSel={clearSel} onOpen={openJD} onDecide={onRoleDecide} onBatch={onBatch} flash={flash} />; break;
    case "watchlist": screen = <window.Watchlist watch={watch} flash={flash} />; break;
    case "applications": screen = <window.Tracker apps={apps} actions={appActions} flash={flash} onOpen={openDetail} dir="ledger" view={view} setView={setView} filter={filter} setFilter={setFilter} />; break;
    case "apply": screen = <window.Apply packet={A.packet} tailoring={S.tailoring} facts={S.facts} flash={flash} />; break;
    case "workspace": screen = <window.Workspace data={S.workspace} rounds={A.rounds} flash={flash} />; break;
    case "people": screen = <window.People people={A.people} warmPaths={A.warmPaths} introDraft={A.introDraft} flash={flash} />; break;
    case "offers": screen = <window.Offers data={S.offers} flash={flash} />; break;
    case "insights": screen = <window.StudioInsights data={S.insights} momentum={A.momentum} patterns={A.patterns} />; break;
    case "profile": screen = <window.Intake data={S.intake} gaps={S.gaps} completeness={S.completeness} flash={flash} />; break;
    case "library": screen = <window.Library facts={S.facts} answers={A.answers} flash={flash} />; break;
    case "sources": screen = <window.Sources sources={S.searchSources} prefs={S.searchPrefs} flash={flash} />; break;
    case "settings": screen = <window.Settings profile={profile} flash={flash} />; break;
    default: screen = <window.Today apps={apps} actions={appActions} flash={flash} onOpen={openDetail} dir="ledger" onGoTo={setRoute} />;
  }

  return (
    <div className="shell">
      <aside className="side">
        <div className="side__brand">
          <span className="mk"><span className="head" /><span className="stick" /></span>
          <b>Matchbox</b>
        </div>
        <nav className="side__nav" style={{ flex: "1 1 auto", overflowY: "auto", minHeight: 0 }}>
          {M_NAV.map((it, i) => it.grp
            ? <div className="side__sec" key={"g" + i}>{it.grp}</div>
            : (
              <button key={it.id} className={window.cx("nav", route === it.id && "active")} onClick={() => setRoute(it.id)}>
                <Icon name={it.icon} size={18} />
                <span>{it.label}</span>
                {it.dot === "todo" && todoCount > 0 && <span className="ping" style={{ marginLeft: "auto" }} />}
                {it.badge && badgeVal(it.badge) != null && badgeVal(it.badge) !== 0 && <span className="ndot mono" style={{ marginLeft: "auto" }}>{badgeVal(it.badge)}</span>}
              </button>
            )
          )}
        </nav>

        <div style={{ flex: "0 0 auto" }}>
          <div className="kbar" onClick={() => setPaletteOpen(true)}>
            <Icon name="search" size={15} /> <span>Search or jump to…</span>
            <span className="sp" /><span className="k">⌘K</span>
          </div>
          <window.AssistantChip queue={queue} onOpen={() => setTrayOpen((v) => !v)} />
          <div className="side__foot" style={{ marginTop: 8 }}>
            <window.ProfileSwitcher profiles={profiles} activeId={profileId} onSwitch={setProfileId} flash={flash} />
          </div>
        </div>
      </aside>

      <div className="main">
        <div className="pad" style={{ maxWidth: 1080 }}>{screen}</div>
      </div>

      {detailApp && <window.Detail app={detailApp} actions={appActions} flash={flash} focusNote={detail.note} onClose={() => setDetail(null)} />}
      {jdRole && <window.JDDrawer role={jdRole} onDecide={onRoleDecide} onClose={() => setJd(null)} flash={flash} />}
      {trayOpen && <window.ActivityTray queue={queue} onClose={() => setTrayOpen(false)} onGo={() => { setTrayOpen(false); setRoute("apply"); }} />}
      {paletteOpen && <window.CommandPalette commands={commands} onClose={() => setPaletteOpen(false)} />}

      {toast && (
        <div className="toasts">
          <div className={window.cx("toast", toast.arrival && "arrival")}>
            {toast.arrival ? <span className="ic"><Icon name="sparkles" size={15} /></span> : <Icon name="check-circle" size={16} />}
            {toast.msg}
            {toast.undo && <button className="undo" onClick={() => { toast.undo(); setToast(null); }}>Undo</button>}
            {toast.go && <button className="undo" onClick={() => { toast.go(); setToast(null); }}>Review</button>}
          </div>
        </div>
      )}
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<MatchboxApp />);
