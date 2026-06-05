/* Live Discovery store — API-backed. Fetches the scored-role set and the
   watchlist once; each decision updates local state optimistically (so the card
   advances instantly and Undo works), persists to /api/discovery/*, then
   reconciles the authoritative role(s) the server returns. The external shape
   ({ roles, watch, decide }) matches the in-memory store, so every component is
   unchanged. `decide` returns an undo thunk; for `tailoring`, the run hand-off
   (run id + prompt) is returned so the shell can surface the manual copy. */
import { useCallback, useEffect, useMemo, useState } from "react";
import type { DecisionInput, Role, WatchedCompany } from "../types";
import * as api from "../api/client";

export interface LiveDecisionResult {
  undo: () => void;
  /** Resolves to the manual tailor hand-off (run id + "process run X" prompt)
      for a `tailoring` decision; undefined for other decisions. */
  run?: Promise<{ runId: string; prompt: string } | null>;
}

export interface LiveDiscoveryStore {
  roles: Role[];
  watch: WatchedCompany[];
  decide: (ids: string[], decision: DecisionInput) => LiveDecisionResult;
}

export function useDiscovery(): LiveDiscoveryStore {
  const [roles, setRoles] = useState<Role[]>([]);
  const [watch, setWatch] = useState<WatchedCompany[]>([]);

  useEffect(() => {
    let alive = true;
    api.listRoles().then((list) => { if (alive) setRoles(list); });
    api.listWatch().then((list) => { if (alive) setWatch(list); });
    return () => { alive = false; };
  }, []);

  const reconcile = useCallback((updated: Role[]) => {
    if (!updated.length) return;
    const byId = new Map(updated.map((r) => [r.id, r]));
    setRoles((list) => list.map((r) => byId.get(r.id) ?? r));
  }, []);

  const refreshWatch = useCallback(() => {
    void api.listWatch().then(setWatch);
  }, []);

  const decide = useCallback((ids: string[], decision: DecisionInput): LiveDecisionResult => {
    // Optimistic local update (mirrors the design's applyDecision).
    const prev: Record<string, Role["decision"]> = {};
    setRoles((list) => list.map((r) => {
      if (ids.includes(r.id)) {
        prev[r.id] = r.decision;
        return { ...r, decision: decision === "skip" ? r.decision : decision === "watch" ? "dismissed" : decision };
      }
      return r;
    }));

    // Persist; reconcile authoritative roles; refresh watch on a watch decision.
    const persisted = ids.length === 1
      ? api.decide(ids[0], decision)
      : api.batchDecide(ids, decision);
    void persisted.then((res) => {
      reconcile(res.roles);
      if (decision === "watch") refreshWatch();
    });

    return {
      undo: () => {
        setRoles((list) => list.map((r) => (r.id in prev ? { ...r, decision: prev[r.id] } : r)));
      },
      // The hand-off prompt resolves once the run is created (tailoring only).
      run: decision === "tailoring" ? persisted.then((res) => res.run ?? null) : undefined,
    };
  }, [reconcile, refreshWatch]);

  return useMemo(() => ({ roles, watch, decide }), [roles, watch, decide]);
}
