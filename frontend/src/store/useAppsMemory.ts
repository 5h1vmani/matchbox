/* In-memory tracker store — the design's exact effect logic (store.jsx) running
   in the browser, seeded from the sample fixture. Kept as an offline/dev/test
   backend; the live app uses the API-backed useApps in ./useApps.ts. */
import { useCallback, useMemo, useState } from "react";
import type { Application, EventKind, NextAction, ResponseType, StageId, TrackerActions } from "../types";
import { FLOW, stageLabel } from "../data/stages";
import { buildSampleApps } from "../data/sample";

function defaultActionFor(stage: StageId): NextAction | null {
  switch (stage) {
    case "applied": return { kind: "followup", label: "Send follow-up", due: 5 };
    case "phone": return { kind: "prep", label: "Prep screening notes", due: 2 };
    case "onsite": return { kind: "interview", label: "Onsite interview", due: 3, time: "13:00" };
    case "offer": return { kind: "offer", label: "Respond to offer", due: 5 };
    default: return null;
  }
}

export function useAppsMemory(): [Application[], TrackerActions] {
  const [apps, setApps] = useState<Application[]>(() =>
    buildSampleApps().map((a) => ({ ...a, events: a.events.slice(), notes: a.notes.slice() })),
  );

  const patch = useCallback((id: string, fn: (a: Application) => Application) => {
    setApps((list) => list.map((a) => (a.id === id ? fn({ ...a }) : a)));
  }, []);

  const pushEvent = (a: Application, kind: EventKind, text: string): Application => {
    a.events = [{ daysAgo: 0, kind, text }, ...a.events];
    a.updatedDaysAgo = 0;
    return a;
  };

  const advanceStage = useCallback((id: string) => {
    patch(id, (a) => {
      const i = FLOW.indexOf(a.stage);
      if (i < 0 || i >= FLOW.length - 1) return a;
      const next = FLOW[i + 1];
      pushEvent(a, "advanced", "Moved to " + stageLabel(next).toLowerCase());
      a.stage = next;
      a.nextAction = defaultActionFor(next);
      if (a.appliedDaysAgo === null) a.appliedDaysAgo = 0;
      a.stale = false;
      return a;
    });
  }, [patch]);

  const setStage = useCallback((id: string, stage: StageId) => {
    patch(id, (a) => {
      if (a.stage === stage) return a;
      const closing = stage === "rejected";
      pushEvent(a, closing ? "rejected" : "advanced", closing ? "Marked closed" : "Moved to " + stageLabel(stage).toLowerCase());
      a.stage = stage;
      a.nextAction = closing ? null : defaultActionFor(stage);
      a.stale = false;
      return a;
    });
  }, [patch]);

  const snooze = useCallback((id: string, days = 2) => {
    patch(id, (a) => {
      if (!a.nextAction) return a;
      const base = a.nextAction.due === null ? 0 : a.nextAction.due;
      a.nextAction = { ...a.nextAction, due: base + days };
      return a;
    });
  }, [patch]);

  const remind = useCallback((id: string, days: number) => {
    patch(id, (a) => {
      a.nextAction = a.nextAction ? { ...a.nextAction, due: days } : { kind: "followup", label: "Send follow-up", due: days };
      pushEvent(a, "note", "Reminder set for " + (days === 0 ? "today" : "in " + days + "d"));
      return a;
    });
  }, [patch]);

  const markDone = useCallback((id: string) => {
    patch(id, (a) => {
      const k = a.nextAction && a.nextAction.kind;
      const verbs: Record<string, string> = { followup: "Follow-up sent", thanks: "Thank-you sent", prep: "Prep done", apply: "Applied", interview: "Interview done" };
      const verb = (k && verbs[k]) || "Done";
      pushEvent(a, k === "apply" ? "applied" : k === "interview" ? "screen" : "followup", verb);
      if (k === "apply") { a.stage = "applied"; if (a.appliedDaysAgo === null) a.appliedDaysAgo = 0; }
      a.hasDraft = false;
      a.nextAction = a.stage === "applied" && k === "followup" ? { kind: "wait", label: "Waiting to hear back", due: null } : null;
      return a;
    });
  }, [patch]);

  const logResponse = useCallback((id: string, type: ResponseType) => {
    patch(id, (a) => {
      if (type === "reply") {
        pushEvent(a, "reply", "Heard back, positive");
        if (a.stage === "applied") { a.stage = "phone"; a.nextAction = defaultActionFor("phone"); }
        else a.nextAction = a.nextAction || defaultActionFor(a.stage);
        a.stale = false;
      } else if (type === "rejected") {
        pushEvent(a, "rejected", "No longer moving forward");
        a.stage = "rejected"; a.nextAction = null; a.stale = false;
      } else if (type === "ghosted") {
        pushEvent(a, "note", "Marked as no response");
        a.nextAction = null; a.stale = true;
      }
      return a;
    });
  }, [patch]);

  const addNote = useCallback((id: string, text: string) => {
    if (!text || !text.trim()) return;
    patch(id, (a) => {
      a.notes = [{ daysAgo: 0, text: text.trim() }, ...a.notes];
      a.events = [{ daysAgo: 0, kind: "note", text: "Added a note" }, ...a.events];
      a.updatedDaysAgo = 0;
      return a;
    });
  }, [patch]);

  const toggleStar = useCallback((id: string) => {
    patch(id, (a) => { a.starred = !a.starred; return a; });
  }, [patch]);

  const actions = useMemo<TrackerActions>(() => ({
    advanceStage, setStage, snooze, remind, markDone, logResponse, addNote, toggleStar,
  }), [advanceStage, setStage, snooze, remind, markDone, logResponse, addNote, toggleStar]);

  return [apps, actions];
}
