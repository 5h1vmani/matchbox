/* Setup-progress API client — the onboarding rail's data source. The server
   derives all seven booleans from existing rows on every read (nothing is
   stored), so the Shell just re-fetches on nav changes. A failed fetch returns
   null and the rail simply does not render — setup guidance is never worth an
   error state. */

export interface SetupStep {
  id: string;
  label: string;
  done: boolean;
  /** Visible progress short of done (e.g. some bullets verified, some pending). */
  partial: boolean;
  /** True only for the first not-done step. */
  active: boolean;
}

export interface SetupState {
  steps: SetupStep[];
  /** Index of the first not-done step; steps.length when setup is complete. */
  current: number;
}

export async function getSetupState(): Promise<SetupState | null> {
  try {
    const r = await fetch("/api/setup/state");
    return r.ok ? ((await r.json()) as SetupState) : null;
  } catch {
    return null;
  }
}
