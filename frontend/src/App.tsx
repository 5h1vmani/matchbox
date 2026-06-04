/* Matchbox — app shell. Sidebar + routing + toast + detail drawer.
   Ported from designs/v1/App.jsx. v1 ships the approved defaults (ledger /
   regular / taupe); the design-time Tweaks panel is intentionally excluded.
   The userchip gains a profile switcher (multi-user requirement). */
import { type ReactNode, useEffect, useMemo, useRef, useState } from "react";
import type { Application, Direction } from "./types";
import { cx } from "./lib/derive";
import { Icon } from "./ui/icon";
import { useApps } from "./store/useApps";
import * as api from "./api/client";
import type { ProfileInfo, UserInfo } from "./api/client";
import { Today } from "./screens/Today";
import { Tracker } from "./screens/Tracker";
import { Detail } from "./screens/Detail";
import { Insights } from "./screens/Insights";

interface NavDef {
  id: string;
  label: string;
  icon: string;
}

const NAV_MAIN: NavDef[] = [
  { id: "today", label: "Today", icon: "sun" },
  { id: "applications", label: "Applications", icon: "layout-list" },
  { id: "saved", label: "Saved roles", icon: "bookmark" },
];
const NAV_WS: NavDef[] = [
  { id: "insights", label: "Insights", icon: "chart-line" },
  { id: "documents", label: "Documents", icon: "file-text" },
  { id: "settings", label: "Settings", icon: "settings" },
];

const DIR: Direction = "ledger";
const DENSITY = "regular";

function NavItem({ it, nav, onNav, meta, todoCount }: {
  it: NavDef;
  nav: string;
  onNav: (id: string) => void;
  meta: Record<string, number | undefined>;
  todoCount: number;
}) {
  return (
    <button className={cx("nav", nav === it.id && "active")} onClick={() => onNav(it.id)}>
      <Icon name={it.icon} size={18} />
      <span>{it.label}</span>
      {it.id === "today" && todoCount > 0 && <span className="ping" title={todoCount + " to do"} />}
      {meta[it.id] != null && <span className="n">{meta[it.id]}</span>}
    </button>
  );
}

function UserSwitcher({ profile, users }: { profile: ProfileInfo; users: UserInfo[] }) {
  const [open, setOpen] = useState(false);
  const pick = (slug: string) => {
    setOpen(false);
    if (slug === profile.slug) return;
    void api.switchUser(slug).then(() => window.location.reload());
  };
  return (
    <div className="side__foot" style={{ position: "relative" }}>
      {open && users.length > 0 && (
        <div className="menu up" style={{ position: "absolute", bottom: "100%", left: 8, right: 8, marginBottom: 8 }}>
          <div className="menu__sec">Switch profile</div>
          {users.map((u) => (
            <button key={u.slug} className="mitem" onClick={() => pick(u.slug)}>
              <Icon name={u.active ? "check" : "user"} size={15} /> {u.name}
            </button>
          ))}
        </div>
      )}
      <button
        className="userchip"
        onClick={() => setOpen((v) => !v)}
        title="Switch profile"
        style={{ width: "100%", border: 0, background: "none", cursor: "pointer", font: "inherit", textAlign: "left" }}
      >
        <span className="av">{profile.initials}</span>
        <div>
          <div className="nm">{profile.name}</div>
          <div className="sub"><span className="live" /> Saved locally</div>
        </div>
        {users.length > 1 && <Icon name="chevrons-up-down" size={15} style={{ marginLeft: "auto", color: "var(--faint-foreground)" }} />}
      </button>
    </div>
  );
}

function Sidebar({ nav, onNav, counts, todoCount, profile, users }: {
  nav: string;
  onNav: (id: string) => void;
  counts: Record<string, number | undefined>;
  todoCount: number;
  profile: ProfileInfo;
  users: UserInfo[];
}) {
  const meta: Record<string, number | undefined> = { applications: counts._total, saved: counts.saved };
  return (
    <aside className="side">
      <div className="side__brand">
        <span className="mk"><span className="head" /><span className="stick" /></span>
        <b>Matchbox</b>
      </div>
      <nav className="side__nav">
        {NAV_MAIN.map((it) => <NavItem key={it.id} it={it} nav={nav} onNav={onNav} meta={meta} todoCount={todoCount} />)}
        <div className="side__sec">Workspace</div>
        {NAV_WS.map((it) => <NavItem key={it.id} it={it} nav={nav} onNav={onNav} meta={meta} todoCount={todoCount} />)}
      </nav>
      <UserSwitcher profile={profile} users={users} />
    </aside>
  );
}

interface DetailState {
  id: string;
  note: boolean;
}

const DEFAULT_PROFILE: ProfileInfo = { name: "", initials: "", slug: "" };

export function App() {
  const [apps, actions] = useApps();
  const [profile, setProfile] = useState<ProfileInfo>(DEFAULT_PROFILE);
  const [users, setUsers] = useState<UserInfo[]>([]);
  const [nav, setNav] = useState("today");
  const [view, setView] = useState("list");
  const [filter, setFilter] = useState("all");
  const [detail, setDetail] = useState<DetailState | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    void api.getProfile().then(setProfile);
    void api.listUsers().then(setUsers);
  }, []);

  const flash = (msg: string) => {
    setToast(msg);
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setToast(null), 2400);
  };

  const openDetail = (app: Application, mode?: string) => setDetail({ id: app.id, note: mode === "note" });
  const detailApp = useMemo(() => (detail ? apps.find((a) => a.id === detail.id) : undefined), [detail, apps]);

  const counts = useMemo(() => {
    const c: Record<string, number> = { _total: apps.length };
    apps.forEach((a) => { c[a.stage] = (c[a.stage] || 0) + 1; });
    return c;
  }, [apps]);

  const todoCount = useMemo(() =>
    apps.filter((a) => a.nextAction && a.nextAction.due !== null && a.nextAction.due <= 1 && a.stage !== "rejected" && a.nextAction.kind !== "wait").length,
  [apps]);

  const goNav = (id: string) => {
    if (id === "documents" || id === "settings") {
      flash(id === "documents" ? "Documents would open here" : "Settings would open here");
      return;
    }
    setNav(id);
    if (id === "saved") setFilter("saved");
    if (id === "applications") setFilter("all");
  };

  let screen: ReactNode;
  if (nav === "today") screen = <Today apps={apps} actions={actions} flash={flash} onOpen={openDetail} dir={DIR} onGoTo={goNav} />;
  else if (nav === "insights") screen = <Insights apps={apps} dir={DIR} />;
  else screen = <Tracker apps={apps} actions={actions} flash={flash} onOpen={openDetail} dir={DIR} view={view} setView={setView} filter={filter} setFilter={setFilter} />;

  return (
    <div className="shell" data-dir={DIR} data-density={DENSITY}>
      <Sidebar nav={nav} onNav={goNav} counts={counts} todoCount={todoCount} profile={profile} users={users} />
      <div className="main">
        <div className="pad">{screen}</div>
      </div>

      {detailApp && <Detail app={detailApp} actions={actions} flash={flash} focusNote={detail?.note} onClose={() => setDetail(null)} />}

      {toast && (
        <div className="toasts"><div className="toast"><Icon name="check-circle" size={16} /> {toast}</div></div>
      )}
    </div>
  );
}
