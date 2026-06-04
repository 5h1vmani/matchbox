/* Stage definitions — presentational SSOT for the pipeline, copied verbatim
   from designs/v1/data.js. The backend defines the same enum independently for
   its CHECK constraint + effects (see matchbox/tracker/rules.py); this is the
   source of truth for labels + tones in the UI. */
import type { Stage, StageId } from "../types";

export const STAGES: Stage[] = [
  { id: "saved", label: "Saved", short: "Saved", tone: "#a1a1aa" },
  { id: "applied", label: "Applied", short: "Applied", tone: "#574747" },
  { id: "phone", label: "Phone screen", short: "Screen", tone: "#2f5d72" },
  { id: "onsite", label: "Onsite", short: "Onsite", tone: "#8a5a1f" },
  { id: "offer", label: "Offer", short: "Offer", tone: "#2f6b46" },
  { id: "rejected", label: "Closed", short: "Closed", tone: "#b8b8bd" },
];

/** Linear progression. `rejected` ("Closed") is off-flow and terminal. */
export const FLOW: StageId[] = ["saved", "applied", "phone", "onsite", "offer"];

export function stageMeta(id: string): Stage {
  return (
    STAGES.find((x) => x.id === id) ?? {
      id: id as StageId,
      label: id,
      short: id,
      tone: "#a1a1aa",
    }
  );
}

export function stageLabel(id: string): string {
  return stageMeta(id).label;
}

export function stageIndex(id: string): number {
  return STAGES.findIndex((x) => x.id === id);
}
