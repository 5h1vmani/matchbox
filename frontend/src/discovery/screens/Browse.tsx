/* Matchbox — Discovery: Browse. Calm filters (not a query builder), a grid of
   roles, and multi-select for the batch hand-off. "Eligible only" defaults on.
   Ported byte-identical from designs/v1.1/Browse.jsx; window.* globals swapped
   for ES imports, the unused `flash` prop dropped. */
import { useEffect, useMemo, useRef, useState } from "react";
import type { DecisionInput, Role } from "../types";
import { dcx, EligibilityRead, FIT_META, Freshness, fullLoc, Icon, MonoLogo } from "../dui";

function ChipRead({ role }: { role: Role }) {
  const fm = FIT_META[role.fit.level] || FIT_META.good;
  return (
    <span className="chipread" style={{ background: fm.bg, color: fm.tone }}>
      <span className="dots">{[0, 1, 2, 3].map((i) => <span key={i} className="dot" style={{ background: i < fm.dots ? fm.tone : "rgba(0,0,0,.12)" }} />)}</span>
      {fm.label}
    </span>
  );
}

interface TileProps {
  role: Role;
  selected: boolean;
  onToggleSel: (id: string) => void;
  onOpen: (role: Role) => void;
  onDecide: (role: Role, decision: DecisionInput) => void;
}

function RoleTile({ role, selected, onToggleSel, onOpen, onDecide }: TileProps) {
  const dimmed = role.eligibility.status === "ineligible" || role.freshness === "closed";
  return (
    <div className={dcx("rtile", selected && "sel", dimmed && "dimmed")} onClick={() => onOpen(role)}>
      <button className={dcx("rtile__sel", selected && "on")} title="Select"
        onClick={(e) => { e.stopPropagation(); onToggleSel(role.id); }}>
        <Icon name="check" size={13} />
      </button>
      <div className="rtile__head">
        <MonoLogo role={role} size={36} radius={8} />
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="rtile__title">{role.title}</div>
          <div className="rtile__co">{role.company} · {fullLoc(role)}</div>
        </div>
      </div>
      <div className="rtile__reads">
        <ChipRead role={role} />
        <EligibilityRead elig={role.eligibility} compact />
      </div>
      <div className="rtile__foot">
        <span className="sal">{role.salary || "Salary undisclosed"}</span>
        <span className="sp" />
        <Freshness role={role} />
        <div className="rtile__acts" onClick={(e) => e.stopPropagation()}>
          {!dimmed && <button className="iconbtn" title="Tailor CV" onClick={() => onDecide(role, "tailoring")}><Icon name="sparkles" size={16} /></button>}
          {!dimmed && <button className="iconbtn" title="Track" onClick={() => onDecide(role, "tracked")}><Icon name="bookmark-plus" size={16} /></button>}
        </div>
      </div>
    </div>
  );
}

const FRESH_FILTERS = [
  { id: "all", label: "All" },
  { id: "new", label: "New this week" },
  { id: "closing", label: "Closing soon" },
];
const FIT_FILTERS: { id: string; label: string; tone?: string }[] = [
  { id: "all", label: "Any fit" },
  { id: "strong", label: "Strong", tone: "#2f6b46" },
  { id: "good", label: "Good", tone: "#574747" },
  { id: "stretch", label: "Stretch", tone: "#8a5a1f" },
];
const SORTS = [
  { id: "fit", label: "Best fit" },
  { id: "newest", label: "Newest" },
  { id: "closing", label: "Closing soon" },
  { id: "salary", label: "Salary disclosed" },
];
const FITRANK: Record<string, number> = { strong: 0, good: 1, stretch: 2 };
const PAGE = 60; // render cap; "Show more" grows it (7k+ roles must not all mount at once)
const SKEY = "mb.browse"; // session-persisted filter bundle
const INDIA_KEY = "mb.review.indiaOnly"; // shared with Today's roles, kept in sync

function loadBrowseState(): Record<string, unknown> {
  try { return JSON.parse(sessionStorage.getItem(SKEY) || "{}"); } catch { return {}; }
}
function indiaDefault(): boolean {
  try { return localStorage.getItem(INDIA_KEY) !== "0"; } catch { return true; }
}

interface BrowseProps {
  roles: Role[];
  sel: Set<string>;
  onToggleSel: (id: string) => void;
  onClearSel: () => void;
  onOpen: (role: Role) => void;
  onDecide: (role: Role, decision: DecisionInput) => void;
  onBatch: (decision: DecisionInput) => void;
}

export function Browse({ roles, sel, onToggleSel, onClearSel, onOpen, onDecide, onBatch }: BrowseProps) {
  const saved = useRef(loadBrowseState()).current;
  const [q, setQ] = useState<string>((saved.q as string) ?? "");
  const [eligibleOnly, setEligibleOnly] = useState<boolean>((saved.eligibleOnly as boolean) ?? true);
  const [fresh, setFresh] = useState<string>((saved.fresh as string) ?? "all");
  const [fit, setFit] = useState<string>((saved.fit as string) ?? "all");
  const [remoteOnly, setRemoteOnly] = useState<boolean>((saved.remoteOnly as boolean) ?? false);
  const [sort, setSort] = useState<string>((saved.sort as string) ?? "fit");
  const [indiaOnly, setIndiaOnly] = useState<boolean>(indiaDefault);
  const [manualOnly, setManualOnly] = useState<boolean>((saved.manualOnly as boolean) ?? false);
  const [visible, setVisible] = useState(PAGE);

  // Persist the transient filters (session) and the India preference (localStorage,
  // shared with Today's roles so the two screens stay in sync).
  useEffect(() => {
    try { sessionStorage.setItem(SKEY, JSON.stringify({ q, eligibleOnly, fresh, fit, remoteOnly, sort, manualOnly })); } catch { /* ignore */ }
  }, [q, eligibleOnly, fresh, fit, remoteOnly, sort, manualOnly]);
  useEffect(() => {
    try { localStorage.setItem(INDIA_KEY, indiaOnly ? "1" : "0"); } catch { /* ignore */ }
  }, [indiaOnly]);
  // A changed filter/search resets paging back to the top.
  useEffect(() => { setVisible(PAGE); }, [q, eligibleOnly, fresh, fit, remoteOnly, sort, indiaOnly, manualOnly]);

  const terms = useMemo(() => q.toLowerCase().split(/\s+/).filter(Boolean), [q]);

  const list = useMemo(() => {
    const out = roles.filter((r) => {
      if (r.decision === "dismissed" || r.decision === "tracked" || r.decision === "tailoring") return false;
      if (eligibleOnly && r.eligibility.status === "ineligible") return false;
      if (eligibleOnly && r.freshness === "closed") return false;
      // A role you added by hand is exempt from the India filter -- you vouched for it.
      if (indiaOnly && r.indiaEligible === false && !r.manual) return false;
      if (manualOnly && !r.manual) return false;
      if (remoteOnly && !r.remote) return false;
      if (fit !== "all" && r.fit.level !== fit) return false;
      if (fresh === "new" && r.postedDaysAgo > 7) return false;
      if (fresh === "closing" && r.freshness !== "closing") return false;
      // Tokenized search across company + role + location: every word must hit.
      if (terms.length) {
        const hay = `${r.company} ${r.title} ${r.location}`.toLowerCase();
        if (!terms.every((t) => hay.includes(t))) return false;
      }
      return true;
    });
    out.sort((a, b) => {
      if (sort === "newest") return a.postedDaysAgo - b.postedDaysAgo;
      if (sort === "salary") {
        const av = a.salary ? 0 : 1, bv = b.salary ? 0 : 1;
        if (av !== bv) return av - bv; // disclosed first, then best fit
        return FITRANK[a.fit.level] - FITRANK[b.fit.level];
      }
      // "fit" (default) and "closing" both lead with closing-soon, as before.
      const ac = a.freshness === "closing" ? 0 : 1, bc = b.freshness === "closing" ? 0 : 1;
      if (ac !== bc) return ac - bc;
      if (sort === "closing" && a.freshness === "closing" && b.freshness === "closing") {
        return (a.closingInDays ?? 1e9) - (b.closingInDays ?? 1e9);
      }
      return FITRANK[a.fit.level] - FITRANK[b.fit.level];
    });
    return out;
  }, [roles, eligibleOnly, fresh, fit, remoteOnly, indiaOnly, manualOnly, sort, terms]);

  const shown = list.slice(0, visible);
  const anyActive = !!q || fit !== "all" || fresh !== "all" || !eligibleOnly || remoteOnly || !indiaOnly || manualOnly || sort !== "fit";
  const clearAll = () => {
    setQ(""); setFit("all"); setFresh("all"); setEligibleOnly(true); setRemoteOnly(false); setIndiaOnly(true); setManualOnly(false); setSort("fit");
  };

  return (
    <div>
      <div className="disc-head">
        <div>
          <h1>Browse roles</h1>
          <p className="sub">Every open role we're tracking for you. Search or filter, then pick. Select a few to tailor at once.</p>
        </div>
      </div>

      {/* search + sort */}
      <div style={{ display: "flex", gap: 10, alignItems: "center", marginBottom: 10, flexWrap: "wrap" }}>
        <div style={{ position: "relative", flex: "1 1 260px", minWidth: 200 }}>
          <Icon name="search" size={15} style={{ position: "absolute", left: 11, top: "50%", transform: "translateY(-50%)", color: "var(--muted-foreground)", pointerEvents: "none" }} />
          <input
            className="inp"
            style={{ width: "100%", paddingLeft: 32, paddingRight: q ? 30 : 11 }}
            placeholder="Search company, role, or location"
            value={q}
            onChange={(e) => setQ(e.target.value)}
            aria-label="Search roles by company, role, or location"
          />
          {q && (
            <button className="iconbtn" title="Clear search" onClick={() => setQ("")}
              style={{ position: "absolute", right: 4, top: "50%", transform: "translateY(-50%)" }}>
              <Icon name="x" size={14} />
            </button>
          )}
        </div>
        <label style={{ display: "inline-flex", alignItems: "center", gap: 8, fontSize: 13, color: "var(--muted-foreground)", whiteSpace: "nowrap" }}>
          Sort
          <select className="inp" value={sort} onChange={(e) => setSort(e.target.value)} style={{ padding: "7px 10px" }}>
            {SORTS.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
          </select>
        </label>
      </div>

      <div className="filters">
        <div className="fgroup">
          {FIT_FILTERS.map((f) => (
            <button key={f.id} className={dcx("fchip", fit === f.id && "active")} onClick={() => setFit(f.id)}>
              {f.tone && <span className="dot" style={{ background: f.tone }} />}{f.label}
            </button>
          ))}
        </div>
        <span className="fsep" />
        <div className="fgroup">
          {FRESH_FILTERS.map((f) => (
            <button key={f.id} className={dcx("fchip", fresh === f.id && "active")} onClick={() => setFresh(f.id)}>{f.label}</button>
          ))}
        </div>
        <span className="fsep" />
        <button className={dcx("fchip", "toggle", eligibleOnly && "active")} onClick={() => setEligibleOnly((v) => !v)}>
          <Icon name={eligibleOnly ? "check" : "circle"} size={13} /> Eligible only
        </button>
        <button className={dcx("fchip", "toggle", remoteOnly && "active")} onClick={() => setRemoteOnly((v) => !v)}>
          <Icon name={remoteOnly ? "check" : "circle"} size={13} /> Remote
        </button>
        <button className={dcx("fchip", "toggle", indiaOnly && "active")} onClick={() => setIndiaOnly((v) => !v)}
          title="Roles you can work from India (in-country or India-remote)">
          <Icon name={indiaOnly ? "check" : "circle"} size={13} /> India-eligible
        </button>
        <button className={dcx("fchip", "toggle", manualOnly && "active")} onClick={() => setManualOnly((v) => !v)}
          title="Only roles you added by hand">
          <Icon name={manualOnly ? "check" : "circle"} size={13} /> Added by me
        </button>
        {anyActive && (
          <>
            <span className="fsep" />
            <button className="fchip" onClick={clearAll}><Icon name="x" size={13} /> Clear all</button>
          </>
        )}
      </div>

      <div className="fbar2">
        <span className="fcount"><b>{list.length}</b> role{list.length !== 1 ? "s" : ""}</span>
        {!eligibleOnly && <span className="fcount" style={{ color: "var(--faint-foreground)" }}>· including ones you may not be eligible for</span>}
      </div>

      {list.length === 0 ? (
        <div className="quiet" style={{ border: "1px solid var(--border)", borderRadius: 12, background: "var(--card)" }}>
          <div className="big">No roles match {q ? `“${q}”` : "these filters"}.</div>
          {anyActive ? (
            <button className="btn ghost small" style={{ marginTop: 10 }} onClick={clearAll}>Clear all filters</button>
          ) : "Try widening fit or freshness."}
        </div>
      ) : (
        <>
          <div className="rgrid">
            {shown.map((role) => (
              <RoleTile key={role.id} role={role} selected={sel.has(role.id)}
                onToggleSel={onToggleSel} onOpen={onOpen} onDecide={onDecide} />
            ))}
          </div>
          {list.length > visible && (
            <button className="showmore" onClick={() => setVisible((v) => v + PAGE)}>
              Show {Math.min(PAGE, list.length - visible)} more <Icon name="chevron-down" size={15} />
            </button>
          )}
        </>
      )}

      {sel.size > 0 && (
        <div className="batch">
          <span className="batch__n"><b>{sel.size}</b> selected</span>
          <button className="btn tiny" onClick={() => onBatch("tracked")}><Icon name="bookmark-plus" size={14} /> Track all</button>
          <button className="btn tiny" onClick={() => onBatch("dismissed")}><Icon name="x" size={14} /> Dismiss</button>
          <button className="btn accent tiny" onClick={() => onBatch("tailoring")}><Icon name="sparkles" size={14} /> Tailor {sel.size} CV{sel.size > 1 ? "s" : ""}</button>
          <button className="batch__x" onClick={onClearSel} title="Clear"><Icon name="x" size={16} /></button>
        </div>
      )}
    </div>
  );
}
