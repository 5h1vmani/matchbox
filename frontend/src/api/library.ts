/* Library API client — the component editor's data layer. The library is the
   verified store of your raw facts: experiences and their bullets, standalone
   projects, skills, and summary variants. A model only ever pulls from what
   lives here, and only after you confirm it; this client never invents anything.
   The server returns the exact view-models, so the screen renders them unchanged.
   Every call is wrapped: the read falls back to an empty library, writes fall
   back to null (or false for deletes) so the UI can leave the row untouched on
   failure. A duplicate skill comes back as 409 — surfaced as a distinct result
   so the screen can flash a calm, honest message instead of swallowing it. */

export interface Tag {
  id: number;
  facet: string;
  value: string;
}

export interface Bullet {
  id: number;
  experienceId: number;
  text: string;
  hasMetric: boolean;
  verified: boolean;
  tags: Tag[];
}

export interface Experience {
  id: number;
  company: string;
  role: string;
  startDate: string | null;
  endDate: string | null;
  location: string | null;
  bullets: Bullet[];
}

export interface Project {
  id: number;
  name: string;
  text: string;
  url: string | null;
  verified: boolean;
  tags: Tag[];
}

export interface Skill {
  id: number;
  name: string;
  category: string | null;
  proficiency: string | null;
}

export interface Summary {
  id: number;
  label: string;
  text: string;
}

export interface LibraryState {
  experiences: Experience[];
  projects: Project[];
  skills: Skill[];
  summaries: Summary[];
}

/** The item kinds the tag endpoints accept. `summary_variant` is the on-the-wire
    name for a Summary. */
export type TagItemType = "bullet" | "project" | "skill" | "summary_variant";

/** A skill write either succeeds (the new skill), fails plainly (null), or is
    rejected as a duplicate name (409) — kept distinct so the screen can speak to
    it without guessing. */
export interface SkillResult {
  skill: Skill | null;
  duplicate: boolean;
}

const JSON_HEADERS = { "Content-Type": "application/json" };

const EMPTY_LIBRARY: LibraryState = {
  experiences: [],
  projects: [],
  skills: [],
  summaries: [],
};

async function getJSON<T>(url: string, fallback: T): Promise<T> {
  try {
    const r = await fetch(url);
    return r.ok ? ((await r.json()) as T) : fallback;
  } catch {
    return fallback;
  }
}

async function sendJSON<T>(url: string, method: string, fallback: T, body?: unknown): Promise<T> {
  try {
    const r = await fetch(url, {
      method,
      headers: JSON_HEADERS,
      body: body ? JSON.stringify(body) : undefined,
    });
    return r.ok ? ((await r.json()) as T) : fallback;
  } catch {
    return fallback;
  }
}

async function del(url: string): Promise<boolean> {
  try {
    const r = await fetch(url, { method: "DELETE" });
    return r.ok;
  } catch {
    return false;
  }
}

export const getLibrary = () => getJSON<LibraryState>("/api/library", EMPTY_LIBRARY);

/* Experiences ----------------------------------------------------------------- */

export interface NewExperience {
  company: string;
  role: string;
  start_date?: string;
  end_date?: string;
  location?: string;
}

export const addExperience = (body: NewExperience) =>
  sendJSON<Experience | null>("/api/library/experiences", "POST", null, body);

export const deleteExperience = (id: number) => del(`/api/library/experiences/${id}`);

/* Bullets --------------------------------------------------------------------- */

export interface NewBullet {
  experience_id: number;
  text: string;
  has_metric?: boolean;
}

export interface BulletPatch {
  text?: string;
  has_metric?: boolean;
  facts_verified?: boolean;
}

export const addBullet = (body: NewBullet) =>
  sendJSON<Bullet | null>("/api/library/bullets", "POST", null, body);

export const patchBullet = (id: number, body: BulletPatch) =>
  sendJSON<Bullet | null>(`/api/library/bullets/${id}`, "PATCH", null, body);

export const deleteBullet = (id: number) => del(`/api/library/bullets/${id}`);

/* Projects -------------------------------------------------------------------- */

export interface NewProject {
  name: string;
  text: string;
  url?: string;
}

export const addProject = (body: NewProject) =>
  sendJSON<Project | null>("/api/library/projects", "POST", null, body);

export const deleteProject = (id: number) => del(`/api/library/projects/${id}`);

/* Skills ---------------------------------------------------------------------- */

export interface NewSkill {
  name: string;
  category?: string;
  proficiency?: string;
}

/** Distinguishes a duplicate (409) from a plain failure so the screen can flash
    a calm message rather than silently dropping the add. */
export async function addSkill(body: NewSkill): Promise<SkillResult> {
  try {
    const r = await fetch("/api/library/skills", {
      method: "POST",
      headers: JSON_HEADERS,
      body: JSON.stringify(body),
    });
    if (r.status === 409) return { skill: null, duplicate: true };
    const skill = r.ok ? ((await r.json()) as Skill) : null;
    return { skill, duplicate: false };
  } catch {
    return { skill: null, duplicate: false };
  }
}

export const deleteSkill = (id: number) => del(`/api/library/skills/${id}`);

/* Summaries ------------------------------------------------------------------- */

export interface NewSummary {
  label: string;
  text: string;
}

export const addSummary = (body: NewSummary) =>
  sendJSON<Summary | null>("/api/library/summaries", "POST", null, body);

export const deleteSummary = (id: number) => del(`/api/library/summaries/${id}`);

/* Tags ------------------------------------------------------------------------ */

export interface NewTag {
  facet: string;
  value: string;
}

export const addTag = (itemType: TagItemType, itemId: number, body: NewTag) =>
  sendJSON<Tag | null>(`/api/library/tags/${itemType}/${itemId}`, "POST", null, body);

export const deleteTag = (itemType: TagItemType, itemId: number, tagId: number) =>
  del(`/api/library/tags/${itemType}/${itemId}/${tagId}`);
