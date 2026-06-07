/* Matchbox — the unified app shell. One sidebar, one router, both data stores:
   Track (today / applications / insights) + Discover (review / browse /
   watchlist), plus a Workspace group linking the still-Jinja utility pages.
   Replaces the separate App.tsx + DiscoveryApp.tsx shells so the two surfaces
   feel like one product (no cross-shell page reloads). Screens are unchanged. */
import { Fragment, type ReactNode, useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { Application } from "./types";
import type { DecisionInput, Role } from "./discovery/types";
import { cx } from "./lib/derive";
import { Icon } from "./ui/icon";
import * as tapi from "./api/client";
import type { ProfileInfo, UserInfo } from "./api/client";
import * as dapi from "./discovery/api/client";
import { useApps } from "./store/useApps";
import { useDiscovery } from "./discovery/store/useDiscovery";
import { useDiscoveryMemory } from "./discovery/store/useDiscoveryMemory";
import { Today } from "./screens/Today";
import { Tracker } from "./screens/Tracker";
import { Insights } from "./screens/Insights";
import { Detail } from "./screens/Detail";
import { Settings } from "./screens/Settings";
import { Answers } from "./screens/Answers";
import { Apply } from "./screens/Apply";
import { Intake } from "./screens/Intake";
import { ReviewFacts } from "./screens/ReviewFacts";
import { Library } from "./screens/Library";
import { Profile } from "./screens/Profile";
import { Sources } from "./screens/Sources";
import { Offers } from "./screens/Offers";
import { Workspace } from "./screens/Workspace";
import { Review } from "./discovery/screens/Review";
import { Browse } from "./discovery/screens/Browse";
import { JDDrawer, Watchlist } from "./discovery/screens/WatchlistJD";
import { CommandPalette, type Command } from "./ui/Palette";

const DIR = "ledger" as const;
const QUEUE_CAP = 20;
const USE_SAMPLE = new URLSearchParams(window.location.search).has("sample");

const DECISION_TOAST: Record<string, string> = {
  tracked: "Tracked. It's in your applications.",
  tailoring: "Queued to tailor.",
  dismissed: "Dismissed. You won't see it again.",
  watch: "Added the company to your watchlist.",
  skip: "Skipped. We'll bring it back tomorrow.",
};

interface NavDef {
  id: string;
  label: string;
  icon: string;
  group: string;
  href?: string; // a Workspace link to a (still-Jinja) page
}
const NAV: NavDef[] = [
  { id: "today", label: "Today", icon: "sun", group: "Track" },
  { id: "applications", label: "Applications", icon: "layout-list", group: "Track" },
  { id: "apply", label: "Apply packet", icon: "file-text", group: "Track" },
  { id: "workspace", label: "Workspace", icon: "users", group: "Track" },
  { id: "offers", label: "Offers", icon: "party-popper", group: "Track" },
  { id: "insights", label: "Insights", icon: "chart-line", group: "Track" },
  { id: "review", label: "Today's roles", icon: "sparkles", group: "Discover" },
  { id: "browse", label: "Browse", icon: "search", group: "Discover" },
  { id: "watchlist", label: "Watchlist", icon: "bookmark", group: "Discover" },
  { id: "library", label: "Library", icon: "book-open", group: "Workspace" },
  { id: "answers", label: "Answers", icon: "messages-square", group: "Workspace" },
  { id: "verify", label: "Review facts", icon: "check-circle", group: "Workspace" },
  { id: "onboarding", label: "Onboarding", icon: "upload", group: "Workspace" },
  { id: "sources", label: "Sources", icon: "rss", group: "Workspace" },
  { id: "settings", label: "Settings", icon: "settings", group: "Workspace" },
  { id: "profile", label: "Profile", icon: "user", group: "Workspace" },
];
const GROUPS = ["Track", "Discover", "Workspace"];

// URL first path segment -> nav id, so a direct hit / refresh on any surface
// opens the right screen (the backend serves the SPA for every non-API route).
const PATH_NAV: Record<string, string> = {
  discover: "review",
  review: "verify",
  apply: "apply",
  library: "library",
  onboarding: "onboarding",
  sources: "sources",
  profile: "profile",
  workspace: "workspace",
  offers: "offers",
  answers: "answers",
  settings: "settings",
  insights: "insights",
  applications: "applications",
};
function initialNav(): string {
  const seg = window.location.pathname.split("/")[1] || "";
  return PATH_NAV[seg] ?? "today";
}

function UserSwitcher({ profile, users }: { profile: ProfileInfo; users: UserInfo[] }) {
  const [open, setOpen] = useState(false);
  const pick = (slug: string) => {
    setOpen(false);
    if (slug === profile.slug) return;
    void tapi.switchUser(slug).then(() => window.location.reload());
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

function Sidebar({ nav, onNav, onPalette, appsCount, todoCount, queueCount, profile, users }: {
  nav: string;
  onNav: (it: NavDef) => void;
  onPalette: () => void;
  appsCount: number;
  todoCount: number;
  queueCount: number;
  profile: ProfileInfo;
  users: UserInfo[];
}) {
  const item = (it: NavDef) => (
    <button key={it.id} className={cx("nav", nav === it.id && "active")} onClick={() => onNav(it)}>
      <Icon name={it.icon} size={18} />
      <span>{it.label}</span>
      {it.id === "today" && todoCount > 0 && <span className="ping" title={todoCount + " to do"} />}
      {it.id === "review" && queueCount > 0 && <span className="ndot mono">{queueCount}</span>}
      {it.id === "applications" && appsCount > 0 && <span className="n">{appsCount}</span>}
      {it.href && <Icon name="arrow-up-right" size={14} style={{ marginLeft: "auto", color: "var(--faint-foreground)" }} />}
    </button>
  );
  return (
    <aside className="side">
      <div className="side__brand">
        <span className="mk"><span className="head" /><span className="stick" /></span>
        <b>Matchbox</b>
      </div>
      <button className="kbar" onClick={onPalette} title="Command palette">
        <Icon name="search" size={15} />
        <span>Jump to…</span>
        <span className="sp" />
        <span className="k">⌘K</span>
      </button>
      <nav className="side__nav">
        {GROUPS.map((g) => (
          <Fragment key={g}>
            <div className="side__sec">{g}</div>
            {NAV.filter((it) => it.group === g).map(item)}
          </Fragment>
        ))}
      </nav>
      <UserSwitcher profile={profile} users={users} />
    </aside>
  );
}

export function Shell() {
  // Both stores live in one shell.
  const [apps, actions] = useApps();
  const live = useDiscovery();
  const mem = useDiscoveryMemory();
  const { roles, watch } = USE_SAMPLE ? mem : live;
  type RunHandoff = { runId: string; prompt: string } | null;
  const decide = useCallback((ids: string[], decision: DecisionInput): { undo: () => void; run?: Promise<RunHandoff> } => {
    if (USE_SAMPLE) return { undo: mem.decide(ids, decision) };
    return live.decide(ids, decision);
  }, [live, mem]);

  const [profile, setProfile] = useState<ProfileInfo>({ name: "", initials: "", slug: "" });
  const [users, setUsers] = useState<UserInfo[]>([]);
  useEffect(() => {
    void tapi.getProfile().then(setProfile);
    void tapi.listUsers().then(setUsers);
  }, []);

  const [nav, setNav] = useState(initialNav);
  const [view, setView] = useState("list");
  const [filter, setFilter] = useState("all");
  const [detail, setDetail] = useState<{ id: string; note: boolean } | null>(null);
  const [jd, setJd] = useState<string | null>(null);
  const [jdRole, setJdRole] = useState<Role | null>(null);
  const [sel, setSel] = useState<Set<string>>(() => new Set());
  const [toast, setToast] = useState<{ msg: string; undo?: () => void } | null>(null);
  const [handoff, setHandoff] = useState<{ runId: string; prompt: string; count: number } | null>(null);
  const [paletteOpen, setPaletteOpen] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const flash = useCallback((msg: string, undo?: () => void) => {
    setToast({ msg, undo });
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setToast(null), undo ? 4200 : 2400);
  }, []);

  // ── tracker ──
  const openDetail = (app: Application, mode?: string) => setDetail({ id: app.id, note: mode === "note" });
  const detailApp = useMemo(() => (detail ? apps.find((a) => a.id === detail.id) : undefined), [detail, apps]);
  const todoCount = useMemo(() =>
    apps.filter((a) => a.nextAction && a.nextAction.due !== null && a.nextAction.due <= 1 && a.stage !== "rejected" && a.nextAction.kind !== "wait").length,
  [apps]);

  // ── discovery ──
  const surfaceRun = useCallback((run: Promise<RunHandoff> | undefined, count: number) => {
    if (run) void run.then((h) => { if (h) setHandoff({ ...h, count }); });
  }, []);
  const onDecide = useCallback((role: Role, decision: DecisionInput) => {
    const { undo, run } = decide([role.id], decision);
    flash(DECISION_TOAST[decision] || "Done", undo);
    surfaceRun(run, 1);
  }, [decide, flash, surfaceRun]);
  const toggleSel = useCallback((id: string) => {
    setSel((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  }, []);
  const clearSel = useCallback(() => setSel(new Set()), []);
  const onBatch = useCallback((decision: DecisionInput) => {
    const ids = [...sel];
    const { undo, run } = decide(ids, decision);
    clearSel();
    const verb = decision === "tailoring" ? "Queued " + ids.length + " to tailor." : decision === "tracked" ? "Tracked " + ids.length + " roles." : "Dismissed " + ids.length + ".";
    flash(verb, undo);
    surfaceRun(run, ids.length);
  }, [sel, decide, clearSel, flash, surfaceRun]);
  useEffect(() => {
    if (!jd) { setJdRole(null); return; }
    let alive = true;
    setJdRole(roles.find((r) => r.id === jd) ?? null);
    if (!USE_SAMPLE) void dapi.getRole(jd).then((full) => { if (alive && full) setJdRole(full); });
    return () => { alive = false; };
  }, [jd, roles]);
  const reviewRoles = useMemo(() => {
    const undecidedOpen = roles
      .filter((r) => !r.decision && r.eligibility.status !== "ineligible" && r.freshness !== "closed")
      .sort((a, b) => {
        const ac = a.freshness === "closing" ? 0 : 1, bc = b.freshness === "closing" ? 0 : 1;
        if (ac !== bc) return ac - bc;
        if (a.freshness === "closing" && b.freshness === "closing") return (a.closingInDays as number) - (b.closingInDays as number);
        const rank: Record<string, number> = { strong: 0, good: 1, stretch: 2 };
        return (rank[a.fit.level] ?? 3) - (rank[b.fit.level] ?? 3) || a.postedDaysAgo - b.postedDaysAgo;
      })
      .slice(0, QUEUE_CAP);
    const rest = roles.filter((r) => r.decision || r.eligibility.status === "ineligible" || r.freshness === "closed");
    return [...undecidedOpen, ...rest];
  }, [roles]);
  const queueCount = useMemo(() =>
    reviewRoles.filter((r) => !r.decision && r.eligibility.status !== "ineligible" && r.freshness !== "closed").length,
  [reviewRoles]);

  const onNav = useCallback((it: NavDef) => {
    if (it.href) { window.location.href = it.href; return; }
    setNav(it.id);
    if (it.id === "applications") setFilter("all");
  }, []);

  // ⌘K / Ctrl-K opens the palette from anywhere.
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        setPaletteOpen((v) => !v);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const commands = useMemo<Command[]>(() => {
    const go: Command[] = NAV.map((it) => ({
      id: "go-" + it.id,
      label: it.label,
      group: "Go to",
      icon: it.icon,
      hint: it.href ? "Opens " + it.href : undefined,
      run: () => onNav(it),
    }));
    const actions: Command[] = [
      { id: "act-tailor", label: "Review today's roles", group: "Actions", icon: "sparkles", run: () => setNav("review") },
      { id: "act-settings", label: "AI settings (bring your own key)", group: "Actions", icon: "settings", run: () => setNav("settings") },
    ];
    return [...go, ...actions];
  }, [onNav]);

  let screen: ReactNode;
  if (nav === "review") screen = <Review roles={reviewRoles} onDecide={onDecide} onOpenJD={(r) => setJd(r.id)} onGoBrowse={() => setNav("browse")} />;
  else if (nav === "browse") screen = <Browse roles={roles} sel={sel} onToggleSel={toggleSel} onClearSel={clearSel} onOpen={(r) => setJd(r.id)} onDecide={onDecide} onBatch={onBatch} />;
  else if (nav === "watchlist") screen = <Watchlist watch={watch} flash={flash} />;
  else if (nav === "insights") screen = <Insights apps={apps} dir={DIR} />;
  else if (nav === "workspace") screen = <Workspace flash={flash} />;
  else if (nav === "offers") screen = <Offers flash={flash} />;
  else if (nav === "answers") screen = <Answers flash={flash} />;
  else if (nav === "apply") screen = <Apply flash={flash} />;
  else if (nav === "verify") screen = <ReviewFacts flash={flash} />;
  else if (nav === "onboarding") screen = <Intake flash={flash} />;
  else if (nav === "library") screen = <Library flash={flash} />;
  else if (nav === "sources") screen = <Sources flash={flash} />;
  else if (nav === "profile") screen = <Profile flash={flash} />;
  else if (nav === "settings") screen = <Settings flash={flash} />;
  else if (nav === "applications") screen = <Tracker apps={apps} actions={actions} flash={flash} onOpen={openDetail} dir={DIR} view={view} setView={setView} filter={filter} setFilter={setFilter} />;
  else screen = <Today apps={apps} actions={actions} flash={flash} onOpen={openDetail} dir={DIR} />;

  return (
    <div className="shell" data-dir={DIR} data-density="regular">
      <Sidebar nav={nav} onNav={onNav} onPalette={() => setPaletteOpen(true)} appsCount={apps.length} todoCount={todoCount} queueCount={queueCount} profile={profile} users={users} />
      <div className="main"><div className="pad">{screen}</div></div>

      {paletteOpen && <CommandPalette commands={commands} onClose={() => setPaletteOpen(false)} />}

      {detailApp && <Detail app={detailApp} actions={actions} flash={flash} focusNote={detail?.note} onClose={() => setDetail(null)} />}
      {jdRole && <JDDrawer role={jdRole} onDecide={onDecide} onClose={() => setJd(null)} flash={flash} />}

      {toast && (
        <div className="toasts">
          <div className="toast">
            <Icon name="check-circle" size={16} /> {toast.msg}
            {toast.undo && <button className="undo" onClick={() => { toast.undo!(); setToast(null); }}>Undo</button>}
          </div>
        </div>
      )}
      {handoff && (
        <div className="handoff">
          <button className="handoff__x" onClick={() => setHandoff(null)} title="Dismiss"><Icon name="x" size={16} /></button>
          <div className="handoff__h"><Icon name="sparkles" size={15} /> {handoff.count > 1 ? handoff.count + " roles queued to tailor" : "Queued to tailor"}</div>
          <p className="handoff__p">Run this in Claude Code to draft {handoff.count > 1 ? "the CVs" : "your CV"}:</p>
          <div className="handoff__cmd">
            <code>{handoff.prompt}</code>
            <button className="btn tiny" onClick={() => { void navigator.clipboard?.writeText(handoff.prompt); flash("Copied. Paste it into Claude Code."); }}>Copy</button>
          </div>
        </div>
      )}
    </div>
  );
}
