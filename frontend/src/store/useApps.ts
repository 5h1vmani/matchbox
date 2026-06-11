/* Live tracker store — API-backed. Fetches the application list once, and each
   action calls the matching endpoint and swaps the returned (authoritative)
   record into local state. The external [apps, actions] shape is identical to
   the in-memory store, so every component is unchanged. */
import { useCallback, useEffect, useMemo, useState } from "react";
import type { Application, TrackerActions } from "../types";
import * as api from "../api/client";

export function useApps(): [Application[], TrackerActions, boolean] {
  const [apps, setApps] = useState<Application[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    api.listApplications().then((list) => { if (alive) { setApps(list); setLoading(false); } });
    return () => { alive = false; };
  }, []);

  const replace = useCallback((updated: Application | null) => {
    if (updated) setApps((list) => list.map((a) => (a.id === updated.id ? updated : a)));
  }, []);

  const run = useCallback((p: Promise<Application | null>) => { void p.then(replace); }, [replace]);

  const actions = useMemo<TrackerActions>(() => ({
    advanceStage: (id) => run(api.advance(id)),
    setStage: (id, stage) => run(api.setStage(id, stage)),
    snooze: (id, days) => run(api.snooze(id, days)),
    remind: (id, days) => run(api.remind(id, days)),
    markDone: (id) => run(api.markDone(id)),
    logResponse: (id, type) => run(api.logResponse(id, type)),
    addNote: (id, text) => run(api.addNote(id, text)),
    toggleStar: (id) => run(api.toggleStar(id)),
  }), [run]);

  return [apps, actions, loading];
}
