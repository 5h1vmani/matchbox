/* Matchbox — Applications tracker. Pipeline overview + list/board, inline
   actions. Ported verbatim from designs/v1/Tracker.jsx. */
import { useMemo, useState } from "react";
import type { Application, Direction, Flash, OpenDetail, TrackerActions } from "../types";
import { STAGES } from "../data/stages";
import { cx, dueVal, updatedText } from "../lib/derive";
import { Icon } from "../ui/icon";
import { Badge, Due, MonoLogo, StageDot } from "../ui/atoms";
import { Funnel, PipeBar, QuickButton, StarBtn } from "../ui/parts";

interface Group {
  id: string;
  label: string;
  items: Application[];
  cold: number;
}

function StaleHint({ app }: { app: Application }) {
  return (
    <Badge tone="neutral" dot>
      <span style={{ color: "var(--faint-foreground)" }}>cold · {app.updatedDaysAgo}d</span>
    </Badge>
  );
}

function Row({ app, actions, flash, onOpen }: { app: Application; actions: TrackerActions; flash: Flash; onOpen: OpenDetail }) {
  const a = app.nextAction;
  return (
    <div className={cx("row", app.stale && "stale")} onClick={() => onOpen(app)}>
      <div className="coname">
        <MonoLogo app={app} size={34} />
        <div style={{ minWidth: 0 }}>
          <div className="nm">{app.company}{app.starred && <Icon name="star" size={12} style={{ fill: "#c79a3b", color: "#c79a3b" }} />}</div>
          <div className="rl">{app.role}</div>
        </div>
      </div>

      {a && a.kind !== "wait" ? (
        <div className="cell-next">
          <span className="lbl">{a.label}</span>
          <Due due={a.due} short />
          {app.hasDraft && (a.kind === "followup" || a.kind === "thanks") && <Badge tone="accent">draft</Badge>}
        </div>
      ) : app.stale ? (
        <div className="cell-next"><StaleHint app={app} /></div>
      ) : a && a.kind === "wait" ? (
        <div className="cell-next none"><span className="lbl">Waiting to hear back</span></div>
      ) : (
        <div className="cell-next none"><span className="lbl">No action needed</span></div>
      )}

      <div className="cell-meta">
        <div className="sal mono">{app.salary}</div>
        <div className="upd">{app.stage === "saved" ? "saved " + updatedText(app.updatedDaysAgo) : "updated " + updatedText(app.updatedDaysAgo)}</div>
      </div>

      <div className="row-actions" onClick={(e) => e.stopPropagation()}>
        <div className="quick">
          <StarBtn app={app} actions={actions} />
        </div>
        <QuickButton app={app} actions={actions} flash={flash} onOpen={onOpen} />
      </div>
    </div>
  );
}

function ListView({ groups, actions, flash, onOpen }: { groups: Group[]; actions: TrackerActions; flash: Flash; onOpen: OpenDetail }) {
  if (groups.every((g) => g.items.length === 0)) {
    return (
      <div className="list">
        <div className="quiet"><div className="big">No applications match.</div>Try a different stage or clear the search.</div>
      </div>
    );
  }
  return (
    <div className="list">
      {groups.map((g) =>
        g.items.length === 0 ? null : (
          <div className="list__group" key={g.id}>
            <div className="glabel">
              <StageDot stage={g.id} />
              <span className="t">{g.label}</span>
              <span className="n mono">{g.items.length}</span>
              {g.id !== "saved" && g.id !== "rejected" && g.cold > 0 && <span className="sp" />}
              {g.cold > 0 && g.id !== "rejected" && <span className="shown">{g.cold} going cold</span>}
            </div>
            {g.items.map((app) => <Row key={app.id} app={app} actions={actions} flash={flash} onOpen={onOpen} />)}
          </div>
        ),
      )}
    </div>
  );
}

function BoardCard({ app, onOpen }: { app: Application; onOpen: OpenDetail }) {
  return (
    <div className={cx("bcard", app.stale && "stale")} onClick={() => onOpen(app)}>
      <div className="top">
        <MonoLogo app={app} size={26} radius={6} />
        <div className="nm">{app.company}</div>
        {app.starred && <Icon name="star" size={13} style={{ fill: "#c79a3b", color: "#c79a3b", marginLeft: "auto" }} />}
      </div>
      <div className="rl">{app.role}</div>
      <div className="foot">
        <span className="sal mono">{app.salary}</span>
        {app.nextAction && app.nextAction.due !== null && app.nextAction.kind !== "wait"
          ? <Due due={app.nextAction.due} short />
          : app.stale ? <StaleHint app={app} />
          : <span className="due later">{updatedText(app.updatedDaysAgo)}</span>}
      </div>
    </div>
  );
}

function BoardView({ groups, onOpen }: { groups: Group[]; onOpen: OpenDetail }) {
  return (
    <div className="board">
      {groups.map((g) => (
        <div className="col" key={g.id}>
          <div className="col__head">
            <StageDot stage={g.id} />
            <span className="t">{g.label}</span>
            <span className="n mono">{g.items.length}</span>
          </div>
          <div className="col__body">
            {g.items.length === 0
              ? <div className="quiet" style={{ padding: "16px 8px", fontSize: 12.5 }}>Empty</div>
              : g.items.map((app) => <BoardCard key={app.id} app={app} onOpen={onOpen} />)}
          </div>
        </div>
      ))}
    </div>
  );
}

interface TrackerProps {
  apps: Application[];
  actions: TrackerActions;
  flash: Flash;
  onOpen: OpenDetail;
  dir: Direction;
  view: string;
  setView: (v: string) => void;
  filter: string;
  setFilter: (f: string) => void;
}

export function Tracker({ apps, actions, flash, onOpen, dir, view, setView, filter, setFilter }: TrackerProps) {
  const [query, setQuery] = useState("");
  const [sort, setSort] = useState("due");

  const counts = useMemo(() => {
    const c: Record<string, number> = {};
    apps.forEach((a) => { c[a.stage] = (c[a.stage] || 0) + 1; });
    return c;
  }, [apps]);

  const filtered = useMemo(() => {
    const q = query.trim().toLowerCase();
    let list = apps;
    if (filter !== "all") list = list.filter((a) => a.stage === filter);
    if (q) list = list.filter((a) => (a.company + " " + a.role + " " + a.location).toLowerCase().includes(q));
    return [...list].sort((x, y) => {
      if (sort === "due") return dueVal(x) - dueVal(y);
      if (sort === "updated") return x.updatedDaysAgo - y.updatedDaysAgo;
      if (sort === "company") return x.company.localeCompare(y.company);
      return 0;
    });
  }, [apps, filter, query, sort]);

  const groups = useMemo<Group[]>(() =>
    STAGES.map((s) => ({
      id: s.id,
      label: s.label,
      items: filtered.filter((a) => a.stage === s.id),
      cold: filtered.filter((a) => a.stage === s.id && a.stale).length,
    })),
  [filtered]);

  const offers = counts.offer || 0;
  const sortLabel = sort === "due" ? "Next action" : sort === "updated" ? "Last updated" : "Company";

  return (
    <div>
      <div className="phead">
        <div>
          <h1>Applications</h1>
          <p className="sub">
            <b>{apps.length}</b> roles in your pipeline.
            {offers > 0 ? <span> <b>{offers}</b> offer{offers > 1 ? "s" : ""} on the table.</span> : " Keep going."}
          </p>
        </div>
        <div className="hgap">
          <div className="seg">
            <button className={cx(view === "list" && "active")} onClick={() => setView("list")}><Icon name="list" size={15} /> List</button>
            <button className={cx(view === "board" && "active")} onClick={() => setView("board")}><Icon name="columns-3" size={15} /> Board</button>
          </div>
          <button className="btn" onClick={() => { window.location.href = "/discover"; }}><Icon name="plus" size={16} /> Add</button>
        </div>
      </div>

      {/* pipeline visualization — funnel in focus, segmented bar in ledger */}
      <div className="card" style={{ padding: "16px 18px", marginBottom: 18 }}>
        <div className="sec-h" style={{ marginBottom: 14 }}>
          <span className="t">Pipeline</span>
          <span className="sp" />
          <span className="shown">{filtered.length} shown</span>
        </div>
        {dir === "focus"
          ? <Funnel counts={counts} active={filter} onPick={setFilter} />
          : <PipeBar counts={counts} total={apps.length} active={filter} onPick={setFilter} />}
      </div>

      <div className="toolbar">
        <div className="search">
          <Icon name="search" size={16} />
          <input placeholder="Search company, role, location" value={query} onChange={(e) => setQuery(e.target.value)} />
        </div>
        <div className="spacer" />
        <button className="btn ghost small" onClick={() => setSort((s) => (s === "due" ? "updated" : s === "updated" ? "company" : "due"))}>
          <Icon name="arrow-down-up" size={14} /> {sortLabel}
        </button>
      </div>

      {view === "list"
        ? <ListView groups={groups} actions={actions} flash={flash} onOpen={onOpen} />
        : <BoardView groups={groups} onOpen={onOpen} />}
    </div>
  );
}
