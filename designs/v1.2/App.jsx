/* Matchbox — app shell. Sidebar + routing + toast + Tweaks (direction switch). */
const { useState: useAppState, useMemo: useAppMemo, useEffect: useAppFx } = React;

const TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "direction": "ledger",
  "density": "regular",
  "accent": "taupe"
}/*EDITMODE-END*/;

const ACCENTS = {
  taupe:  { "--oat-600": "#574747", "--oat-700": "#473a3a", "--oat-100": "#ede8e8", "--oat-300": "#b6a6a6" },
  forest: { "--oat-600": "#2f6b46", "--oat-700": "#265739", "--oat-100": "#e3efe7", "--oat-300": "#a9c8b4" },
  slate:  { "--oat-600": "#2f5d72", "--oat-700": "#264c5e", "--oat-100": "#e2ecf1", "--oat-300": "#a6c0cc" },
};

const NAV_MAIN = [
  { id: "today", label: "Today", icon: "sun" },
  { id: "applications", label: "Applications", icon: "layout-list" },
  { id: "saved", label: "Saved roles", icon: "bookmark" },
];
const NAV_WS = [
  { id: "insights", label: "Insights", icon: "chart-line" },
  { id: "documents", label: "Documents", icon: "file-text" },
  { id: "settings", label: "Settings", icon: "settings" },
];

function Sidebar({ nav, onNav, counts, todoCount }) {
  const meta = { applications: counts._total, saved: counts.saved };
  const Item = ({ it }) => (
    <button className={window.cx("nav", nav === it.id && "active")} onClick={() => onNav(it.id)}>
      <Icon name={it.icon} size={18} />
      <span>{it.label}</span>
      {it.id === "today" && todoCount > 0 && <span className="ping" title={todoCount + " to do"} />}
      {meta[it.id] != null && <span className="n">{meta[it.id]}</span>}
    </button>
  );
  return (
    <aside className="side">
      <div className="side__brand">
        <span className="mk"><span className="head" /><span className="stick" /></span>
        <b>Matchbox</b>
      </div>
      <nav className="side__nav">
        {NAV_MAIN.map((it) => <Item key={it.id} it={it} />)}
        <div className="side__sec">Workspace</div>
        {NAV_WS.map((it) => <Item key={it.id} it={it} />)}
      </nav>
      <div className="side__foot">
        <div className="userchip">
          <span className="av">{window.PROFILE.initials}</span>
          <div>
            <div className="nm">{window.PROFILE.name}</div>
            <div className="sub"><span className="live" /> Saved locally</div>
          </div>
        </div>
      </div>
    </aside>
  );
}

function App() {
  const [apps, actions] = window.useApps();
  const [t, setTweak] = useTweaks(TWEAK_DEFAULTS);
  const [nav, setNav] = useAppState("today");
  const [view, setView] = useAppState("list");
  const [filter, setFilter] = useAppState("all");
  const [detail, setDetail] = useAppState(null); // { id, note }
  const [toast, setToast] = useAppState(null);

  const dir = t.direction;

  useAppFx(() => {
    const root = document.documentElement;
    const set = ACCENTS[t.accent] || ACCENTS.taupe;
    Object.entries(set).forEach(([k, v]) => root.style.setProperty(k, v));
  }, [t.accent]);

  const flash = (msg) => { setToast(msg); clearTimeout(window.__t); window.__t = setTimeout(() => setToast(null), 2400); };

  const openDetail = (app, mode) => setDetail({ id: app.id, note: mode === "note" });
  const detailApp = useAppMemo(() => detail && apps.find((a) => a.id === detail.id), [detail, apps]);

  const counts = useAppMemo(() => {
    const c = { _total: apps.length };
    apps.forEach((a) => c[a.stage] = (c[a.stage] || 0) + 1);
    return c;
  }, [apps]);

  const todoCount = useAppMemo(() =>
    apps.filter((a) => a.nextAction && a.nextAction.due !== null && a.nextAction.due <= 1 && a.stage !== "rejected" && a.nextAction.kind !== "wait").length,
  [apps]);

  const goNav = (id) => {
    if (id === "documents" || id === "settings") { flash(id === "documents" ? "Documents would open here" : "Settings would open here"); return; }
    setNav(id);
    if (id === "saved") setFilter("saved");
    if (id === "applications") setFilter("all");
  };

  let screen;
  if (nav === "today") screen = <window.Today apps={apps} actions={actions} flash={flash} onOpen={openDetail} dir={dir} onGoTo={goNav} />;
  else if (nav === "insights") screen = <window.Insights apps={apps} dir={dir} />;
  else screen = <window.Tracker apps={apps} actions={actions} flash={flash} onOpen={openDetail} dir={dir} view={view} setView={setView} filter={filter} setFilter={setFilter} />;

  return (
    <div className="shell" data-dir={dir} data-density={t.density}>
      <Sidebar nav={nav} onNav={goNav} counts={counts} todoCount={todoCount} />
      <div className="main">
        <div className="pad">{screen}</div>
      </div>

      {detailApp && <window.Detail app={detailApp} actions={actions} flash={flash} focusNote={detail.note} onClose={() => setDetail(null)} />}

      {toast && (
        <div className="toasts"><div className="toast"><Icon name="check-circle" size={16} /> {toast}</div></div>
      )}

      <TweaksPanel>
        <TweakSection label="Design direction" />
        <TweakRadio label="Direction" value={t.direction}
          options={[{ value: "ledger", label: "Calm ledger" }, { value: "focus", label: "Focus & flow" }]}
          onChange={(v) => setTweak("direction", v)} />
        <p style={{ fontSize: 12, color: "var(--muted-foreground)", margin: "0 0 4px", lineHeight: 1.45 }}>
          {dir === "focus"
            ? "A warm hero surfaces the single most important next thing; the pipeline reads as a funnel."
            : "Cool and restrained. A checklist-style Today and a proportional pipeline bar."}
        </p>
        <TweakSection label="Feel" />
        <TweakRadio label="Density" value={t.density}
          options={[{ value: "regular", label: "Regular" }, { value: "compact", label: "Compact" }]}
          onChange={(v) => setTweak("density", v)} />
        <TweakRadio label="Accent" value={t.accent}
          options={[{ value: "taupe", label: "Taupe" }, { value: "forest", label: "Forest" }, { value: "slate", label: "Slate" }]}
          onChange={(v) => setTweak("accent", v)} />
      </TweaksPanel>
    </div>
  );
}

ReactDOM.createRoot(document.getElementById("root")).render(<App />);
