/* Matchbox — Application detail drawer. JTBD #3: log, advance, note, prep —
   without leaving the page. Ported verbatim from designs/v1/Detail.jsx. */
import { useEffect, useRef, useState } from "react";
import type { Application, Flash, TrackerActions } from "../types";
import { FLOW, stageLabel } from "../data/stages";
import { cx, dueInfo, eventIcon } from "../lib/derive";
import { Icon } from "../ui/icon";
import { Badge, MonoLogo, StageStepper } from "../ui/atoms";
import { QuickButton, StarBtn } from "../ui/parts";
import { useDialog } from "../lib/useDialog";
import { listArtifacts, markArtifactSent } from "../api/client";
import type { Artifact } from "../api/client";

function whenText(daysAgo: number): string {
  if (daysAgo <= 0) return "Today";
  if (daysAgo === 1) return "Yesterday";
  if (daysAgo < 7) return daysAgo + " days ago";
  if (daysAgo < 14) return "Last week";
  if (daysAgo < 31) return Math.round(daysAgo / 7) + " weeks ago";
  return Math.round(daysAgo / 30) + " month" + (daysAgo >= 60 ? "s" : "") + " ago";
}

function tlTone(kind: string): string {
  if (kind === "offer" || kind === "reply" || kind === "advanced") return "ok";
  if (kind === "rejected") return "err";
  if (kind === "applied" || kind === "screen" || kind === "onsite") return "accent";
  return "";
}

interface DetailProps {
  app: Application;
  actions: TrackerActions;
  flash: Flash;
  onClose: () => void;
  focusNote?: boolean;
  onTailor?: (app: Application) => void;
}

interface Cta {
  label: string;
  icon: string;
  run: () => void;
}

export function Detail({ app, actions, flash, onClose, focusNote, onTailor }: DetailProps) {
  const [note, setNote] = useState("");
  const [tailorQueued, setTailorQueued] = useState(false);
  const noteRef = useRef<HTMLTextAreaElement>(null);
  const dialogRef = useDialog<HTMLDivElement>(onClose);
  useEffect(() => { if (focusNote && noteRef.current) noteRef.current.focus(); }, [focusNote]);

  // Fetch draft artifact when the drawer opens for an app that has one.
  const [draftArtifact, setDraftArtifact] = useState<Artifact | null>(null);
  const [copyFlash, setCopyFlash] = useState(false);
  useEffect(() => {
    if (!app.hasDraft) { setDraftArtifact(null); return; }
    void listArtifacts(app.id).then((arts) => {
      const draft = [...arts].reverse().find(
        (a) => (a.kind === "followup" || a.kind === "thankyou") && a.status === "draft",
      ) ?? null;
      setDraftArtifact(draft);
    });
  }, [app.id, app.hasDraft]);

  const copyDraft = () => {
    if (!draftArtifact?.body) return;
    void navigator.clipboard.writeText(draftArtifact.body).then(() => {
      setCopyFlash(true);
      setTimeout(() => setCopyFlash(false), 2000);
    });
  };

  const a = app.nextAction;
  const i = FLOW.indexOf(app.stage);
  const nextStage = i >= 0 && i < FLOW.length - 1 ? FLOW[i + 1] : null;
  const closed = app.stage === "rejected";

  const primaryCta = (): Cta | null => {
    if (!a) return null;
    const map: Record<string, Cta> = {
      followup: { label: "Mark sent", icon: "check", run: () => { actions.markDone(app.id); flash("Marked sent to " + app.company); if (draftArtifact) void markArtifactSent(app.id, draftArtifact.id).catch(() => {}); } },
      thanks: { label: "Mark sent", icon: "check", run: () => { actions.markDone(app.id); flash("Marked sent."); if (draftArtifact) void markArtifactSent(app.id, draftArtifact.id).catch(() => {}); } },
      apply: { label: "Mark applied", icon: "check", run: () => { actions.markDone(app.id); flash("Marked applied to " + app.company); } },
      prep: { label: "Mark prepped", icon: "check", run: () => { actions.markDone(app.id); flash("Prep done"); } },
      interview: { label: "Mark done", icon: "check", run: () => { actions.markDone(app.id); flash("Interview logged"); } },
      offer: { label: "Accept offer", icon: "party-popper", run: () => { actions.setStage(app.id, "offer"); flash("Congratulations on the offer"); } },
    };
    return map[a.kind] ?? null;
  };
  const cta = primaryCta();

  const submitNote = () => { if (note.trim()) { actions.addNote(app.id, note); setNote(""); flash("Note saved"); } };

  return (
    <div className="scrim" onMouseDown={(e) => { if (e.target === e.currentTarget) onClose(); }}>
      <div className="drawer" ref={dialogRef} role="dialog" aria-modal="true" aria-label={app.company} tabIndex={-1} onMouseDown={(e) => e.stopPropagation()}>
        <div className="drawer__top">
          <button className="iconbtn" onClick={onClose} title="Close"><Icon name="x" size={18} /></button>
          <span className="sp" />
          <StarBtn app={app} actions={actions} size={16} />
          {app.jobUrl && (
            <a className="iconbtn" href={app.jobUrl} target="_blank" rel="noreferrer" title="Open job post">
              <Icon name="external-link" size={16} />
            </a>
          )}
          {app.cvUrl && (
            <a className="iconbtn" href={app.cvUrl} target="_blank" rel="noreferrer" title="Open tailored CV (PDF)">
              <Icon name="file-text" size={16} />
            </a>
          )}
          <QuickButton app={app} actions={actions} flash={flash} onOpen={() => {}} />
        </div>

        <div className="drawer__body">
          <div className="dhdr">
            <MonoLogo app={app} size={52} radius={12} />
            <div style={{ minWidth: 0 }}>
              <div className="nm">{app.company}</div>
              <div className="rl">{app.role}</div>
              <div className="tags">
                <Badge tone={closed ? "neutral" : "cool"} dot>{stageLabel(app.stage)}</Badge>
                <Badge tone="neutral"><Icon name="map-pin" size={11} /> {app.location}</Badge>
                <Badge tone="neutral"><Icon name="banknote" size={11} /> {app.salary}</Badge>
              </div>
            </div>
          </div>

          <StageStepper stage={app.stage} />

          {/* Next action card */}
          {a && a.kind !== "wait" ? (
            <div className="dnext">
              <span className="di"><Icon name={eventIcon(a.kind === "followup" ? "followup" : a.kind === "interview" ? "screen" : a.kind)} size={19} /></span>
              <div style={{ minWidth: 0 }}>
                <div className="l">{a.label}{a.time ? " · " + a.time : ""}</div>
                <div className="s">{a.due !== null ? dueInfo(a.due)?.text : "No date set"}{app.hasDraft && (a.kind === "followup" || a.kind === "thanks") ? " · draft ready" : ""}</div>
              </div>
              <div className="cta">
                {a.kind === "apply" && app.jobUrl && (
                  <a className="btn outline small" href={app.jobUrl} target="_blank" rel="noreferrer">
                    <Icon name="external-link" size={14} /> Open posting
                  </a>
                )}
                <button className="btn outline small" onClick={() => { actions.snooze(app.id, 2); flash("Snoozed for 2 days"); }}>Snooze</button>
                {cta && <button className="btn accent small" onClick={cta.run}><Icon name={cta.icon} size={14} /> {cta.label}</button>}
              </div>
            </div>
          ) : closed ? (
            <div className="dnext" style={{ background: "var(--muted)", borderColor: "var(--border)" }}>
              <span className="di" style={{ color: "var(--muted-foreground)" }}><Icon name="archive" size={19} /></span>
              <div><div className="l">Closed</div><div className="s">No further action. This one is logged for your records.</div></div>
              <div className="cta"><button className="btn outline small" onClick={() => { actions.setStage(app.id, "applied"); flash("Reopened"); }}>Reopen</button></div>
            </div>
          ) : (
            <div className="dnext" style={{ background: "var(--muted)", borderColor: "var(--border)" }}>
              <span className="di" style={{ color: "var(--muted-foreground)" }}><Icon name="hourglass" size={18} /></span>
              <div><div className="l">Waiting to hear back</div><div className="s">Applied {app.appliedDaysAgo}d ago · no reply yet</div></div>
              <div className="cta"><button className="btn outline small" onClick={() => { actions.remind(app.id, 0); flash("Follow-up reminder set"); }}><Icon name="reply" size={14} /> Follow up</button></div>
            </div>
          )}

          {/* Tailored CV state: open it, or get one made */}
          <div className="dsec">
            <div className="dsec__h">Tailored CV</div>
            {app.cvUrl ? (
              <a className="btn outline small" href={app.cvUrl} target="_blank" rel="noreferrer">
                <Icon name="file-text" size={14} /> Open CV (PDF)
              </a>
            ) : app.runId || tailorQueued ? (
              <div className="note">
                <div className="nt">
                  Queued for tailoring. Run this in Claude Code to draft it:
                  {app.runId && <> <code className="mono">process run {app.runId}</code></>}
                </div>
                {app.runId && (
                  <button className="btn ghost tiny" style={{ marginTop: 6 }}
                    onClick={() => { void navigator.clipboard?.writeText("process run " + app.runId); flash("Copied. Paste it into Claude Code."); }}>
                    <Icon name="copy" size={13} /> Copy command
                  </button>
                )}
              </div>
            ) : onTailor ? (
              <button className="btn accent small" onClick={() => { setTailorQueued(true); onTailor(app); }}>
                <Icon name="sparkles" size={14} /> Tailor a CV for this role
              </button>
            ) : (
              <div className="note"><div className="nt">No tailored CV yet.</div></div>
            )}
          </div>

          {/* Draft artifact body */}
          {draftArtifact?.body && (
            <div className="dsec">
              <div className="dsec__h">
                Draft: {draftArtifact.kind === "thankyou" ? "thank-you" : "follow-up"}
                <span className="sp" />
                <button className="btn ghost tiny" onClick={copyDraft}>
                  <Icon name="copy" size={13} /> {copyFlash ? "Copied" : "Copy"}
                </button>
              </div>
              <div className="note" style={{ whiteSpace: "pre-wrap", fontFamily: "inherit", fontSize: 13.5, lineHeight: 1.6 }}>
                {draftArtifact.body}
              </div>
            </div>
          )}

          {/* Quick actions */}
          <div className="dsec">
            <div className="dsec__h">Quick actions</div>
            <div className="qgrid">
              {nextStage && (
                <button className="qbtn" onClick={() => { actions.advanceStage(app.id); flash("Moved to " + stageLabel(nextStage).toLowerCase()); }}>
                  <Icon name="arrow-right" size={17} />
                  <span>Advance stage<span className="s">to {stageLabel(nextStage).toLowerCase()}</span></span>
                </button>
              )}
              <button className="qbtn" onClick={() => { actions.logResponse(app.id, "reply"); flash("Logged a reply"); }}>
                <Icon name="mail-check" size={17} />
                <span>Log a reply<span className="s">heard back</span></span>
              </button>
              <button className="qbtn" onClick={() => { actions.remind(app.id, 3); flash("Reminder set for in 3 days"); }}>
                <Icon name="bell" size={17} />
                <span>Set a reminder<span className="s">nudge me later</span></span>
              </button>
              {!closed && (
                <button className="qbtn" onClick={() => { actions.logResponse(app.id, "rejected"); flash(app.company + " marked closed"); }}>
                  <Icon name="x-circle" size={17} />
                  <span>Mark closed<span className="s">honest, no shame</span></span>
                </button>
              )}
            </div>
          </div>

          {/* Details */}
          <div className="dsec">
            <div className="dsec__h">Details</div>
            <div className="dmeta">
              <div className="m"><div className="k"><Icon name="calendar" size={13} /> Applied</div><div className="v">{app.appliedDaysAgo === null ? "Not yet" : whenText(app.appliedDaysAgo)}</div></div>
              <div className="m"><div className="k"><Icon name="activity" size={13} /> Last update</div><div className="v">{whenText(app.updatedDaysAgo)}</div></div>
              <div className="m"><div className="k"><Icon name="banknote" size={13} /> Salary range</div><div className="v mono">{app.salary}</div></div>
              <div className="m"><div className="k"><Icon name="compass" size={13} /> Source</div><div className="v">{app.source}</div></div>
            </div>
          </div>

          {/* Notes */}
          <div className="dsec">
            <div className="dsec__h">Notes <span className="sp" />{app.notes.length > 0 && <span style={{ fontWeight: 400, color: "var(--faint-foreground)" }}>{app.notes.length}</span>}</div>
            {app.notes.map((n, idx) => (
              <div className="note" key={idx}>
                <div className="nt">{n.text}</div>
                <div className="nw">{whenText(n.daysAgo)}</div>
              </div>
            ))}
            <div className="notebox">
              <textarea
                ref={noteRef}
                placeholder="Jot a note: what to ask, who you met, how it felt…"
                value={note}
                onChange={(e) => setNote(e.target.value)}
                onKeyDown={(e) => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) submitNote(); }}
              />
              <button className="btn outline small" onClick={submitNote} disabled={!note.trim()} style={{ alignSelf: "flex-start" }}>Save</button>
            </div>
          </div>

          {/* Contacts */}
          {app.contacts.length > 0 && (
            <div className="dsec">
              <div className="dsec__h">People</div>
              {app.contacts.map((c, idx) => (
                <div className="contact" key={idx}>
                  <span className="av">{c.initials}</span>
                  <div><div className="nm">{c.name}</div><div className="rl">{c.role}</div></div>
                </div>
              ))}
            </div>
          )}

          {/* Timeline */}
          <div className="dsec">
            <div className="dsec__h">History</div>
            <div className="timeline">
              {app.events.map((ev, idx) => (
                <div className="tl" key={idx}>
                  <span className={cx("tl__dot", tlTone(ev.kind))}><Icon name={eventIcon(ev.kind)} size={14} /></span>
                  <div className="tl__body">
                    <div className="tl__t">{ev.text}</div>
                    <div className="tl__when">{whenText(ev.daysAgo)}</div>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
