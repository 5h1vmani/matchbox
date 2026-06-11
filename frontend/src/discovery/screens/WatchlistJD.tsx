/* Matchbox — Discovery: Watchlist + JD drawer (the deeper moment).
   Ported byte-identical from designs/v1.1/WatchlistJD.jsx; window.* globals
   swapped for ES imports. */
import { Fragment } from "react";
import type { DecisionInput, Role, WatchedCompany } from "../types";
import { Coverage, dcx, EligibilityRead, FitMeter, Freshness, fullLoc, Icon, MonoLogo } from "../dui";
import { useDialog } from "../../lib/useDialog";

type Flash = (msg: string) => void;

/* Render one JD paragraph. Consecutive lines starting with "• " (or "- ") from
   the HTML stripper become a real bullet list; other lines become paragraphs. */
function JdBlock({ text }: { text: string }) {
  const lines = text.split("\n").map((l) => l.trim()).filter(Boolean);
  const blocks: { bullet: boolean; items: string[] }[] = [];
  for (const l of lines) {
    const bullet = l.startsWith("• ") || l.startsWith("- ");
    const last = blocks[blocks.length - 1];
    if (last && last.bullet === bullet) last.items.push(l);
    else blocks.push({ bullet, items: [l] });
  }
  return (
    <>
      {blocks.map((b, i) => (
        <Fragment key={i}>
          {b.bullet
            ? <ul>{b.items.map((l, j) => <li key={j}>{l.replace(/^[•-]\s+/, "")}</li>)}</ul>
            : b.items.map((l, j) => <p key={j}>{l}</p>)}
        </Fragment>
      ))}
    </>
  );
}

export function Watchlist({ watch, flash, onUnwatch }: { watch: WatchedCompany[]; flash: Flash; onUnwatch: (company: string) => void }) {
  return (
    <div>
      <div className="disc-head">
        <div>
          <h1>Watchlist</h1>
          <p className="sub">Companies worth watching, even when there's no role for you today. We'll surface openings as they post.</p>
        </div>
      </div>
      {watch.length === 0 ? (
        <div className="quiet">
          <div className="big">Nothing on your watchlist yet.</div>
          Companies land here when you tap "Watch company" on a role card in Today's roles or Browse.
        </div>
      ) : (
      <div className="watch-grid">
        {watch.map((w, i) => (
          <div className="wtile" key={i}>
            <span className="mono-logo" style={{ background: w.mono.bg, color: w.mono.fg, width: 38, height: 38, borderRadius: 9, fontSize: 15, display: "flex", alignItems: "center", justifyContent: "center", fontWeight: 600, flex: "0 0 auto" }}>
              {w.company.slice(0, 1)}
            </span>
            <div className="info">
              <div className="nm">
                {w.company}
                <span className={dcx("wtag", w.status)}>{w.openRoles > 0 ? w.openRoles + " open" : "watching"}</span>
              </div>
              <div className="wnote">{w.note}</div>
            </div>
            <button className="iconbtn bell" title="Stop watching" onClick={() => { onUnwatch(w.company); flash("Stopped watching " + w.company); }}>
              <Icon name="bell-ring" size={16} />
            </button>
          </div>
        ))}
      </div>
      )}
    </div>
  );
}

interface DrawerProps {
  role: Role;
  onDecide: (role: Role, decision: DecisionInput) => void;
  onClose: () => void;
  flash: Flash;
}

/* JD drawer — full description + the rationale alongside. Reuses .scrim/.drawer. */
export function JDDrawer({ role, onDecide, onClose }: DrawerProps) {
  const dialogRef = useDialog<HTMLDivElement>(onClose);
  const dimmed = role.eligibility.status === "ineligible" || role.freshness === "closed";
  return (
    <div className="scrim" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="drawer" ref={dialogRef} role="dialog" aria-modal="true" aria-label={role.title + " at " + role.company} tabIndex={-1} onMouseDown={(e) => e.stopPropagation()}>
        <div className="drawer__top">
          <button className="iconbtn" onClick={onClose} title="Close"><Icon name="x" size={18} /></button>
          <span className="sp" style={{ marginLeft: "auto" }} />
          {role.link ? (
            <a className="iconbtn" href={role.link} target="_blank" rel="noopener noreferrer" title="Open original posting" style={{ textDecoration: "none" }}><Icon name="external-link" size={16} /></a>
          ) : (
            <button className="iconbtn" title="No link available" disabled><Icon name="external-link" size={16} /></button>
          )}
        </div>
        <div className="drawer__body">
          <div className="dhdr" style={{ marginBottom: 16 }}>
            <MonoLogo role={role} size={52} radius={12} />
            <div style={{ minWidth: 0 }}>
              <div className="nm" style={{ fontSize: 20, fontWeight: 600, letterSpacing: "-.015em" }}>{role.title}</div>
              <div className="rl" style={{ fontSize: 14, color: "var(--muted-foreground)", marginTop: 2 }}>{role.company} · {fullLoc(role)}</div>
              <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 10, alignItems: "center" }}>
                <Freshness role={role} />
                {role.salary && <span className="mbadge"><Icon name="banknote" size={11} /> {role.salary}</span>}
                <span className="mbadge"><Icon name="compass" size={11} /> {role.source}</span>
              </div>
            </div>
          </div>

          {/* the two reads, full */}
          <div className="reads" style={{ margin: "0 0 22px" }}>
            <FitMeter fit={role.fit} />
            <EligibilityRead elig={role.eligibility} />
          </div>

          {role.coverage && (
            <div className="jd-section">
              <h4>CV coverage</h4>
              <Coverage coverage={role.coverage} />
              <p style={{ fontSize: 13, color: "var(--muted-foreground)", margin: "10px 0 0", lineHeight: 1.5 }}>
                Tailoring fills the gaps. The assistant will pull from your CV library and rewrite to match this posting's must-haves.
              </p>
            </div>
          )}

          <div className="jd-section">
            <h4>Full description</h4>
            <div className="jd-text">
              {role.jd.map((para, i) => <JdBlock key={i} text={para} />)}
            </div>
            {role.link && (
              <a className="jd-open" href={role.link} target="_blank" rel="noopener noreferrer"
                 style={{ display: "inline-flex", alignItems: "center", gap: 6, marginTop: 12, fontSize: 13, fontWeight: 600, color: "var(--oat-600, #2f5d72)", textDecoration: "none" }}>
                Open original posting <Icon name="external-link" size={14} />
              </a>
            )}
          </div>

          <div className="jd-section">
            <h4>At a glance</h4>
            <div className="jd-meta">
              <div className="m"><div className="k"><Icon name="map-pin" size={13} /> Location</div><div className="v">{fullLoc(role)}</div></div>
              <div className="m"><div className="k"><Icon name="banknote" size={13} /> Salary</div><div className="v mono">{role.salary || "Undisclosed"}</div></div>
              <div className="m"><div className="k"><Icon name="calendar" size={13} /> Posted</div><div className="v">{role.postedDaysAgo}d ago</div></div>
              <div className="m"><div className="k"><Icon name="compass" size={13} /> Source</div><div className="v">{role.source}</div></div>
            </div>
          </div>
        </div>

        {/* sticky decision footer */}
        <div className="rcard__foot" style={{ borderTop: "1px solid var(--border)" }}>
          {dimmed ? (
            <>
              <span style={{ fontSize: 13, color: "var(--muted-foreground)" }}>{role.freshness === "closed" ? "This role has closed." : "Probably out of reach right now."}</span>
              <span className="grow" />
              <button className="btn ghost small btn-dismiss" onClick={() => { onDecide(role, "dismissed"); onClose(); }}>Dismiss</button>
              {role.freshness !== "closed" && <button className="btn outline small" onClick={() => { onDecide(role, "watch"); onClose(); }}><Icon name="bell" size={14} /> Watch company</button>}
            </>
          ) : (
            <>
              <button className="btn ghost small btn-dismiss" onClick={() => { onDecide(role, "dismissed"); onClose(); }}><Icon name="x" size={15} /> Dismiss</button>
              <span className="grow" />
              <button className="btn outline small" onClick={() => { onDecide(role, "tracked"); onClose(); }}><Icon name="bookmark-plus" size={15} /> Track</button>
              <button className="btn accent small" onClick={() => { onDecide(role, "tailoring"); onClose(); }}><Icon name="sparkles" size={15} /> Tailor CV</button>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
