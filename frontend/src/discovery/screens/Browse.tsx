/* Matchbox — Discovery: Browse. Calm filters (not a query builder), a grid of
   roles, and multi-select for the batch hand-off. "Eligible only" defaults on.
   Ported byte-identical from designs/v1.1/Browse.jsx; window.* globals swapped
   for ES imports, the unused `flash` prop dropped. */
import { useMemo, useState } from "react";
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
  const [eligibleOnly, setEligibleOnly] = useState(true);
  const [fresh, setFresh] = useState("all");
  const [fit, setFit] = useState("all");
  const [remoteOnly, setRemoteOnly] = useState(false);

  const list = useMemo(() => {
    return roles.filter((r) => {
      if (r.decision === "dismissed" || r.decision === "tracked" || r.decision === "tailoring") return false;
      if (eligibleOnly && r.eligibility.status === "ineligible") return false;
      if (eligibleOnly && r.freshness === "closed") return false;
      if (remoteOnly && !r.remote) return false;
      if (fit !== "all" && r.fit.level !== fit) return false;
      if (fresh === "new" && r.postedDaysAgo > 7) return false;
      if (fresh === "closing" && r.freshness !== "closing") return false;
      return true;
    }).sort((a, b) => {
      const ac = a.freshness === "closing" ? 0 : 1, bc = b.freshness === "closing" ? 0 : 1;
      if (ac !== bc) return ac - bc;
      return (({ strong: 0, good: 1, stretch: 2 } as Record<string, number>)[a.fit.level]) - (({ strong: 0, good: 1, stretch: 2 } as Record<string, number>)[b.fit.level]);
    });
  }, [roles, eligibleOnly, fresh, fit, remoteOnly]);

  return (
    <div>
      <div className="disc-head">
        <div>
          <h1>Browse roles</h1>
          <p className="sub">Every open role we're tracking for you. Filter, then pick. Select a few to tailor at once.</p>
        </div>
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
      </div>

      <div className="fbar2">
        <span className="fcount"><b>{list.length}</b> role{list.length !== 1 ? "s" : ""}</span>
        {!eligibleOnly && <span className="fcount" style={{ color: "var(--faint-foreground)" }}>· including ones you may not be eligible for</span>}
      </div>

      {list.length === 0 ? (
        <div className="quiet" style={{ border: "1px solid var(--border)", borderRadius: 12, background: "var(--card)" }}>
          <div className="big">No roles match these filters.</div>Try widening fit or freshness.
        </div>
      ) : (
        <div className="rgrid">
          {list.map((role) => (
            <RoleTile key={role.id} role={role} selected={sel.has(role.id)}
              onToggleSel={onToggleSel} onOpen={onOpen} onDecide={onDecide} />
          ))}
        </div>
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
