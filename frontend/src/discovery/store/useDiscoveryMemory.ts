/* In-memory Discovery store — the design's exact decision logic (DiscoveryApp.jsx
   applyDecision / undoDecision / watch-upsert) running in the browser, seeded
   from the sample fixture. Kept as an offline/dev/test backend and as the
   screenshot-parity backend; the live app uses the API-backed useDiscovery. */
import { useCallback, useMemo, useState } from "react";
import type { DecisionInput, Role, WatchedCompany } from "../types";
import { SAMPLE_ROLES, SAMPLE_WATCH } from "../data/discoverySample";

export interface DiscoveryStore {
  roles: Role[];
  watch: WatchedCompany[];
  /** Apply a decision to one role; returns an undo thunk. */
  decide: (ids: string[], decision: DecisionInput) => () => void;
  /** Stop watching a company (removes the tile from the in-memory watchlist). */
  unwatch: (company: string) => void;
}

export function useDiscoveryMemory(): DiscoveryStore {
  const [roles, setRoles] = useState<Role[]>(() => SAMPLE_ROLES.map((r) => ({ ...r })));
  const [watch, setWatch] = useState<WatchedCompany[]>(() => SAMPLE_WATCH.map((w) => ({ ...w })));

  const decide = useCallback((ids: string[], decision: DecisionInput): (() => void) => {
    const prev: Record<string, Role["decision"]> = {};
    setRoles((list) => list.map((r) => {
      if (ids.includes(r.id)) {
        prev[r.id] = r.decision;
        return { ...r, decision: decision === "skip" ? r.decision : decision === "watch" ? "dismissed" : decision };
      }
      return r;
    }));
    if (decision === "watch") {
      setRoles((list) => {
        const role = list.find((r) => ids.includes(r.id));
        if (role) setWatch((w) => w.find((x) => x.company === role.company) ? w : [{ company: role.company, note: "Watching for a role you're eligible for.", status: "watching", openRoles: 0, mono: role.mono }, ...w]);
        return list;
      });
    }
    return () => {
      setRoles((list) => list.map((r) => (r.id in prev ? { ...r, decision: prev[r.id] } : r)));
    };
  }, []);

  const unwatch = useCallback((company: string) => {
    setWatch((w) => w.filter((x) => x.company !== company));
  }, []);

  return useMemo(() => ({ roles, watch, decide, unwatch }), [roles, watch, decide, unwatch]);
}
