/* Matchbox — Today / Focus home. JTBD #1: "tell me what to do now."
   Renders calmer in [data-dir=ledger], with a warm hero in [data-dir=focus]. */
const { useState: useTodayState, useMemo: useTodayMemo } = React;

const RANK = { interview: 0, offer: 0, thanks: 1, prep: 1, apply: 2, followup: 2, wait: 9 };

function greeting() {
  const h = new Date().getHours();
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}
function todayDate() {
  return new Date().toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });
}

function dueVal(a) { return a.nextAction && a.nextAction.due !== null ? a.nextAction.due : 999; }

function TaskRow({ app, actions, flash, onOpen, done, onToggle }) {
  const p = window.actionPhrase(app);
  const isDone = !!done;
  const draftReady = app.hasDraft && app.nextAction && (app.nextAction.kind === "followup" || app.nextAction.kind === "thanks");
  return (
    <div className="task">
      <button className={window.cx("tick", isDone && "done")} title="Mark done"
        onClick={() => onToggle(app)}>
        {isDone && <Icon name="check" size={12} />}
      </button>
      <div className="body" onClick={() => onOpen(app)}>
        <div className={window.cx("lead", isDone && "struck")}>
          <window.ActionLine app={app} />
        </div>
        <div className="meta">{p.sub}</div>
      </div>
      <div className="trail">
        {draftReady && !isDone && <window.Badge tone="accent"><Icon name="check" size={11} /> Draft</window.Badge>}
        {!isDone && app.nextAction && <Due due={app.nextAction.due} />}
        <div className="acts">
          <button className="btn ghost small" title="Snooze 2 days"
            onClick={(e) => { e.stopPropagation(); actions.snooze(app.id, 2); flash("Snoozed for 2 days"); }}>
            <Icon name="alarm-clock" size={14} /> Snooze
          </button>
          <window.QuickButton app={app} actions={actions} flash={flash} onOpen={onOpen} />
        </div>
      </div>
    </div>
  );
}

function UpNext({ app, onOpen }) {
  const a = app.nextAction;
  const di = window.dueInfo(a.due);
  return (
    <div className="upnext">
      <div className="when">
        <div className="d">{di ? di.short : ""}</div>
        {a.time && <div className="t">{a.time}</div>}
      </div>
      <div className="info" onClick={() => onOpen(app)}>
        <div className="l">{a.label} · {app.company}</div>
        <div className="s">{app.role}</div>
      </div>
      <button className="btn outline small" onClick={() => onOpen(app)}>Prep</button>
    </div>
  );
}

function Today({ apps, actions, flash, onOpen, dir, onGoTo }) {
  const [done, setDone] = useTodayState({});
  const [coldOpen, setColdOpen] = useTodayState(false);
  const [expanded, setExpanded] = useTodayState(false);

  const toggleDone = (app) => {
    if (done[app.id]) { setDone((d) => { const n = { ...d }; delete n[app.id]; return n; }); return; }
    setDone((d) => ({ ...d, [app.id]: true }));
    setTimeout(() => { actions.markDone(app.id); flash("Nice, that is logged"); }, 280);
  };

  const todays = useTodayMemo(() => {
    return apps
      .filter((a) => a.nextAction && a.nextAction.due !== null && a.nextAction.due <= 0 && a.stage !== "rejected" && a.nextAction.kind !== "wait")
      .sort((x, y) => (RANK[x.nextAction.kind] - RANK[y.nextAction.kind]) || (dueVal(x) - dueVal(y)));
  }, [apps]);

  const upcoming = useTodayMemo(() =>
    apps.filter((a) => a.nextAction && a.nextAction.kind === "interview" && a.nextAction.due !== null && a.nextAction.due >= 0 && a.nextAction.due <= 7)
      .sort((x, y) => dueVal(x) - dueVal(y)).slice(0, 4), [apps]);

  const drafts = useTodayMemo(() =>
    apps.filter((a) => a.hasDraft && a.stage !== "rejected").slice(0, 4), [apps]);

  const cold = useTodayMemo(() => apps.filter((a) => a.stale), [apps]);

  const offers = useTodayMemo(() => apps.filter((a) => a.stage === "offer"), [apps]);
  const activeCount = apps.filter((a) => ["applied", "phone", "onsite"].includes(a.stage)).length;
  const interviewsWk = apps.filter((a) => a.nextAction && a.nextAction.kind === "interview" && dueVal(a) <= 7).length;

  const visibleTodays = todays.filter((a) => !done[a.id]);
  const top = todays[0] || upcoming[0];
  const CAP = 7;
  const listSource = dir === "focus" && top ? todays.filter((a) => a.id !== top.id) : todays;

  return (
    <div className="today-wrap">
      <div className="greet">
        <div>
          <h1>{greeting()}.</h1>
          <p className="date">{todayDate()}</p>
        </div>
        <div className="glance">
          <div className="g"><div className="v">{visibleTodays.length}</div><div className="k">to do today</div></div>
          <div className="g"><div className="v">{interviewsWk}</div><div className="k">interviews this week</div></div>
          <div className="g"><div className="v">{activeCount}</div><div className="k">active</div></div>
          {offers.length > 0 && <div className="g"><div className="v" style={{ color: "var(--success)" }}>{offers.length}</div><div className="k">offer{offers.length > 1 ? "s" : ""}</div></div>}
        </div>
      </div>

      {/* FOCUS hero — the single most important thing */}
      {dir === "focus" && (
        <div className="hero">
          <div className="hero__eyebrow"><Icon name="target" size={13} /> Right now</div>
          {top ? (
            <div className="hero__row">
              <MonoLogo app={top} size={46} radius={11} />
              <div style={{ minWidth: 0 }}>
                <div className="hero__lead"><window.ActionLine app={top} /></div>
                <div className="hero__sub">{window.actionPhrase(top).sub}{top.nextAction.due !== null && top.nextAction.due <= 0 ? " · due now" : ""}</div>
              </div>
              <div className="hero__cta">
                <button className="btn outline" onClick={() => { actions.snooze(top.id, 2); flash("Snoozed for 2 days"); }}>Snooze</button>
                <button className="btn accent" onClick={() => onOpen(top)}>
                  {top.nextAction.kind === "interview" ? "Prep now" : top.nextAction.kind === "offer" ? "Review offer" : "Do it"} <Icon name="arrow-right" size={15} />
                </button>
              </div>
            </div>
          ) : (
            <div className="hero__none">
              <span className="ring"><Icon name="check" size={22} /></span>
              <div>
                <div className="hero__lead">You're all caught up.</div>
                <div className="hero__sub">Nothing needs you today. Go for a walk.</div>
              </div>
            </div>
          )}
        </div>
      )}

      {/* Due today list */}
      <div className="block">
        <div className="block__h">
          <span className="ic" style={{ background: "var(--oat-100)", color: "var(--oat-600)" }}><Icon name="sun" size={15} /></span>
          <span className="t">{dir === "focus" ? "Also today" : "Today"}</span>
          <span className="n mono">{listSource.filter((a) => !done[a.id]).length}</span>
        </div>
        {listSource.length === 0 ? (
          dir === "ledger"
            ? <div className="quiet"><div className="big">Nothing needs you today.</div>Go for a walk. Your applications are all up to date.</div>
            : <div className="quiet" style={{ padding: "20px 12px", fontSize: 13 }}>Nothing else today. You're on top of it.</div>
        ) : (
          <React.Fragment>
            <div className="tasks">
              {(expanded ? listSource : listSource.slice(0, CAP)).map((app) => (
                <TaskRow key={app.id} app={app} actions={actions} flash={flash} onOpen={onOpen}
                  done={done[app.id]} onToggle={toggleDone} />
              ))}
            </div>
            {listSource.length > CAP && (
              <button className="showmore" onClick={() => setExpanded((v) => !v)}>
                {expanded ? "Show less" : "Show " + (listSource.length - CAP) + " more"}
                <Icon name={expanded ? "chevron-up" : "chevron-down"} size={15} />
              </button>
            )}
          </React.Fragment>
        )}
      </div>

      {/* lower grid: upcoming + drafts */}
      <div className="t-grid">
        <div className="block">
          <div className="block__h">
            <span className="ic" style={{ background: "#e7eef2", color: "#2f5d72" }}><Icon name="calendar-clock" size={15} /></span>
            <span className="t">Upcoming interviews</span>
            <span className="n mono">{upcoming.length}</span>
          </div>
          {upcoming.length === 0
            ? <div className="quiet" style={{ padding: "22px 12px", fontSize: 13 }}>No interviews scheduled. Keep applying.</div>
            : <div>{upcoming.map((app) => <UpNext key={app.id} app={app} onOpen={onOpen} />)}</div>}
        </div>

        <div className="block">
          <div className="block__h">
            <span className="ic" style={{ background: "var(--muted)", color: "var(--secondary-foreground)" }}><Icon name="file-pen-line" size={15} /></span>
            <span className="t">Drafts ready to send</span>
            <span className="n mono">{drafts.length}</span>
          </div>
          {drafts.length === 0
            ? <div className="quiet" style={{ padding: "22px 12px", fontSize: 13 }}>No drafts waiting.</div>
            : <div>{drafts.map((app) => (
              <div className="draft" key={app.id}>
                <span className="di"><Icon name={app.nextAction && app.nextAction.kind === "thanks" ? "heart" : "reply"} size={15} /></span>
                <div className="info" onClick={() => onOpen(app)} style={{ cursor: "pointer" }}>
                  <div className="l">{app.nextAction && app.nextAction.kind === "thanks" ? "Thank-you note" : "Follow-up"} · {app.company}</div>
                  <div className="s">{app.role}</div>
                </div>
                <button className="btn outline small" onClick={() => { actions.markDone(app.id); flash("Sent to " + app.company); }}>
                  <Icon name="send" size={13} /> Send
                </button>
              </div>
            ))}</div>}
        </div>
      </div>

      {/* cooling off — honest, dimmed, collapsible */}
      {cold.length > 0 && (
        <div className={window.cx("cold", coldOpen && "open")}>
          <div className="cold__h" onClick={() => setColdOpen((v) => !v)}>
            <span className="ic"><Icon name="snowflake" size={15} /></span>
            <span className="t">Going cold</span>
            <span className="s">· {cold.length} with no reply in a while</span>
            <span className="chev"><Icon name="chevron-down" size={16} /></span>
          </div>
          {coldOpen && (
            <div className="cold__body">
              {cold.map((app) => (
                <div className="coldrow" key={app.id}>
                  <MonoLogo app={app} size={28} radius={7} />
                  <div className="info" onClick={() => onOpen(app)}>
                    <div className="l">{app.company} · {app.role}</div>
                    <div className="s">No update in {app.updatedDaysAgo} days · {window.stageLabel(app.stage)}</div>
                  </div>
                  <div className="acts">
                    <button className="btn ghost small" onClick={() => { actions.remind(app.id, 0); flash("Follow-up reminder set for today"); }}>
                      <Icon name="reply" size={14} /> Follow up
                    </button>
                    <button className="btn ghost small" onClick={() => { actions.logResponse(app.id, "ghosted"); flash("Marked as no response"); }}>
                      <Icon name="archive" size={14} /> Let go
                    </button>
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

window.Today = Today;
