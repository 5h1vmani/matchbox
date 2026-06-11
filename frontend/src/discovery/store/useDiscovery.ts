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
  loading: boolean;
  decide: (ids: string[], decision: DecisionInput) => LiveDecisionResult;
  /** Stop watching a company. Optimistic; reconciles with the server list. */
  unwatch: (company: string) => void;
}

export function useDiscovery(): LiveDiscoveryStore {
  const [roles, setRoles] = useState<Role[]>([]);
  const [watch, setWatch] = useState<WatchedCompany[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    Promise.all([api.listRoles(), api.listWatch()]).then(([roleList, watchList]) => {
      if (alive) { setRoles(roleList); setWatch(watchList); setLoading(false); }
    });
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
    // Snapshot the previous decision for each role before mutating.
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

    // Undo: only supported when the previous decision is a known DecisionInput
    // value that the server can accept. "skip" never mutates the server so
    // reverting local state is sufficient; all others POST the prior decision
    // back. If a role had no prior decision we can't clear it to "undecided"
    // via the existing API, so we skip that role's server call.
    const supportedDecisions = new Set<string>(["tracked", "tailoring", "dismissed", "watch", "skip"]);
    const canUndo = decision !== "skip" && ids.some((id) => prev[id] != null && supportedDecisions.has(String(prev[id])));

    return {
      undo: canUndo ? () => {
        // Revert local state immediately.
        setRoles((list) => list.map((r) => (r.id in prev ? { ...r, decision: prev[r.id] } : r)));
        // POST the prior decision back to the server for each role that had one.
        for (const id of ids) {
          const prior = prev[id];
          if (prior != null && supportedDecisions.has(String(prior))) {
            void api.decide(id, prior as DecisionInput).then((res) => reconcile(res.roles));
          }
        }
      } : () => {
        // Undo unsupported (no prior decision to restore) — just revert local.
        setRoles((list) => list.map((r) => (r.id in prev ? { ...r, decision: prev[r.id] } : r)));
      },
      // The hand-off prompt resolves once the run is created (tailoring only).
      run: decision === "tailoring" ? persisted.then((res) => res.run ?? null) : undefined,
    };
  }, [reconcile, refreshWatch]);

  const unwatch = useCallback((company: string) => {
    setWatch((w) => w.filter((x) => x.company !== company)); // optimistic
    void api.unwatch(company).then((list) => { if (list) setWatch(list); });
  }, []);

  return useMemo(() => ({ roles, watch, loading, decide, unwatch }), [roles, watch, loading, decide, unwatch]);
}
