/* Matchbox — Discovery: the daily Review queue. One calm card at a time.
   Eligible + open roles only; ineligible/closed are tucked into a set-aside
   group below. Decisions: dismiss / track / tailor (the hand-off).
   Ported byte-identical from designs/v1.1/Review.jsx; window.* globals swapped
   for ES imports, the unused `flash` prop dropped. */
import { Fragment, useEffect, useMemo, useState } from "react";
import type { DecisionInput, Role } from "../types";
import { Coverage, dcx, EligibilityRead, FitMeter, Freshness, fullLoc, Icon, MonoLogo } from "../dui";

function fitRank(level: string): number { return ({ strong: 0, good: 1, stretch: 2 } as Record<string, number>)[level] ?? 3; }

interface CardProps {
  role: Role;
  onDecide: (role: Role, decision: DecisionInput) => void;
  onOpenJD: (role: Role) => void;
  aside?: boolean;
}

/* full review card */
function ReviewCard({ role, onDecide, onOpenJD, aside }: CardProps) {
  const closed = role.freshness === "closed";
  return (
    <div className={dcx("rcard", aside && "aside")}>
      <div className="rcard__body">
        <div className="rcard__head">
          <MonoLogo role={role} size={48} radius={12} />
          <div style={{ minWidth: 0, flex: 1 }}>
            <div className="rcard__title">{role.title}</div>
            <div className="rcard__co">
              <span>{role.company}</span><span className="dotsep" />
              <span>{fullLoc(role)}</span>
              {role.salary && <Fragment><span className="dotsep" /><span className="sal">{role.salary}</span></Fragment>}
            </div>
            <div className="rcard__src">
              <Freshness role={role} plain />
              <span className="dotsep" />
              <span>via {role.source}</span>
            </div>
          </div>
        </div>

        <div className="reads">
          <FitMeter fit={role.fit} />
          <EligibilityRead elig={role.eligibility} />
        </div>

        {role.coverage && <Coverage coverage={role.coverage} />}

        <p className="rcard__pull">{role.jd[0]}</p>

        <button className="jdtoggle" onClick={() => onOpenJD(role)}>
          <Icon name="file-text" size={15} /> Read full description
        </button>
      </div>

      {aside ? (
        <div className="rcard__foot">
          <span style={{ fontSize: 13, color: "var(--muted-foreground)" }}>
            {closed ? "This role has closed." : "Probably out of reach for you right now."}
          </span>
          <span className="grow" />
          <button className="btn ghost small btn-dismiss" onClick={() => onDecide(role, "dismissed")}>Dismiss</button>
          <button className="btn outline small" onClick={() => onDecide(role, "watch")}><Icon name="bell" size={14} /> Watch company</button>
        </div>
      ) : (
        <div className="rcard__foot">
          <button className="btn ghost small btn-dismiss" onClick={() => onDecide(role, "dismissed")}>
            <Icon name="x" size={15} /> Dismiss <span className="kbd">X</span>
          </button>
          <span className="grow" />
          <button className="btn outline small" onClick={() => onDecide(role, "tracked")}>
            <Icon name="bookmark-plus" size={15} /> Track <span className="kbd">T</span>
          </button>
          <button className="btn accent small" onClick={() => onDecide(role, "tailoring")}>
            <Icon name="sparkles" size={15} /> Tailor CV <span className="kbd">⏎</span>
          </button>
        </div>
      )}
    </div>
  );
}

interface ReviewProps {
  roles: Role[];
  onDecide: (role: Role, decision: DecisionInput) => void;
  onOpenJD: (role: Role) => void;
  onGoBrowse: () => void;
}

export function Review({ roles, onDecide, onOpenJD, onGoBrowse }: ReviewProps) {
  const [asideOpen, setAsideOpen] = useState(false);

  // active queue: eligible/unclear + open, undecided. Closing-soon first, then fit.
  const queue = useMemo(() =>
    roles.filter((r) => !r.decision && r.eligibility.status !== "ineligible" && r.freshness !== "closed")
      .sort((a, b) => {
        const ac = a.freshness === "closing" ? 0 : 1, bc = b.freshness === "closing" ? 0 : 1;
        if (ac !== bc) return ac - bc;
        if (a.freshness === "closing" && b.freshness === "closing") return (a.closingInDays as number) - (b.closingInDays as number);
        return fitRank(a.fit.level) - fitRank(b.fit.level) || a.postedDaysAgo - b.postedDaysAgo;
      }), [roles]);

  // set aside: ineligible or closed, undecided
  const aside = useMemo(() =>
    roles.filter((r) => !r.decision && (r.eligibility.status === "ineligible" || r.freshness === "closed")),
  [roles]);

  // tally of decisions made this session
  const tally = useMemo(() => {
    const t: Record<string, number> = { tracked: 0, tailoring: 0, dismissed: 0 };
    roles.forEach((r) => { if (r.decision && t[r.decision] != null) t[r.decision]++; });
    return t;
  }, [roles]);

  const total = queue.length + tally.tracked + tally.tailoring + tally.dismissed;
  const reviewed = total - queue.length;
  const pct = total ? Math.round((reviewed / total) * 100) : 100;
  const current = queue[0];

  // keyboard shortcuts
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (!current) return;
      const tag = (e.target as HTMLElement).tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (e.key === "x" || e.key === "X") onDecide(current, "dismissed");
      else if (e.key === "t" || e.key === "T") onDecide(current, "tracked");
      else if (e.key === "Enter") onDecide(current, "tailoring");
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [current, onDecide]);

  return (
    <div className="review">
      <div className="disc-head" style={{ maxWidth: "none" }}>
        <div>
          <h1>Today's roles</h1>
          <p className="sub">{total > 0
            ? <span>We found <b>{total}</b> fresh role{total > 1 ? "s" : ""} worth a look. Decide on each, or set it aside.</span>
            : <span>Nothing new to review right now.</span>}</p>
        </div>
      </div>

      {current ? (
        <Fragment>
          <div className="qprog">
            <div className="qprog__bar"><div className="qprog__fill" style={{ width: pct + "%" }} /></div>
            <span className="qprog__txt"><b>{reviewed}</b> of {total} reviewed</span>
          </div>
          <ReviewCard role={current} onDecide={onDecide} onOpenJD={onOpenJD} />
          <div style={{ textAlign: "center", marginTop: 14 }}>
            <button className="btn ghost small" onClick={() => onDecide(current, "skip")}>
              Skip for now <span className="kbd" style={{ marginLeft: 6 }}>↓</span>
            </button>
          </div>
        </Fragment>
      ) : (
        <div className="qdone">
          <div className="qdone__ring"><Icon name="check" size={26} /></div>
          <h2>That's today's roles.</h2>
          <p>New roles arrive as companies post them. Nothing else needs you here right now.</p>
          <div className="qdone__tally">
            <div className="t"><div className="v" style={{ color: "var(--oat-600)" }}>{tally.tailoring}</div><div className="k">sent to tailor</div></div>
            <div className="t"><div className="v">{tally.tracked}</div><div className="k">tracked</div></div>
            <div className="t"><div className="v" style={{ color: "var(--faint-foreground)" }}>{tally.dismissed}</div><div className="k">set aside</div></div>
          </div>
          <button className="btn outline" onClick={onGoBrowse}><Icon name="search" size={16} /> Browse all open roles</button>
        </div>
      )}

      {aside.length > 0 && (
        <div className={dcx("aside-group", asideOpen && "open")}>
          <div className="aside-group__h" onClick={() => setAsideOpen((v) => !v)}>
            <span className="ic"><Icon name="archive" size={16} /></span>
            <div>
              <span className="t">Set aside for you</span>
              <span className="s"> · {aside.length} you probably can't apply to</span>
            </div>
            <span className="chev"><Icon name="chevron-down" size={16} /></span>
          </div>
          {asideOpen && (
            <div>
              {aside.map((role) => (
                <div className="aside-row" key={role.id}>
                  <MonoLogo role={role} size={30} radius={7} />
                  <div className="info">
                    <div className="l">{role.title} · {role.company}</div>
                    <div className="s">{role.freshness === "closed" ? "Closed · " + (role.postedDaysAgo - 7) + "d ago" : role.eligibility.reason}</div>
                  </div>
                  <div className="acts">
                    <button className="btn ghost small" onClick={() => onOpenJD(role)}>View</button>
                    {role.freshness !== "closed" && <button className="btn ghost small" onClick={() => onDecide(role, "watch")}><Icon name="bell" size={13} /> Watch</button>}
                    <button className="btn ghost small" onClick={() => onDecide(role, "dismissed")}>Dismiss</button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
