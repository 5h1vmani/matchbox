/* Deterministic sample data — ported verbatim from designs/v1/data.js.
   Used as the dev/offline fixture and as the reference shape for the DB seed.
   No Date usage (relative daysAgo), so it is stable and SSR-safe. */
import type { Application, Contact, NextAction, Note, Profile, TimelineEvent } from "../types";
import { STAGES } from "./stages";

export const SAMPLE_PROFILE: Profile = { name: "Job seeker", file: "job-search.matchbox", initials: "JS" };

type Seed = [company: string, role: string, location: string, salary: string, source: string];

export function buildSampleApps(): Application[] {
  const seeds: Seed[] = [
    ["Linear", "Product Designer", "Remote (US)", "$150–185k", "Referral · Dana"],
    ["Vercel", "Design Engineer", "Remote (US)", "$160–190k", "Careers page"],
    ["Stripe", "Sr. Product Designer", "New York", "$170–210k", "LinkedIn"],
    ["Notion", "Design Engineer", "San Francisco", "$165–195k", "Referral · Wes"],
    ["Figma", "Staff Product Designer", "San Francisco", "$190–230k", "Recruiter reached out"],
    ["Supabase", "Frontend Engineer", "Remote (global)", "$140–170k", "Careers page"],
    ["Ramp", "Product Design Lead", "New York", "$185–220k", "LinkedIn"],
    ["Retool", "UX Engineer", "Remote (US)", "$150–180k", "Careers page"],
    ["Render", "Design Engineer", "Remote (US)", "$140–170k", "Wellfound"],
    ["Fly.io", "Frontend Engineer", "Remote (global)", "$150–180k", "Hacker News"],
    ["PostHog", "Product Designer", "Remote (EU)", "€80–105k", "Careers page"],
    ["Cal.com", "Design Engineer", "Remote (global)", "$130–160k", "GitHub"],
    ["Raycast", "Product Designer", "Remote (EU)", "€75–95k", "Twitter"],
    ["Replicate", "Frontend Engineer", "San Francisco", "$160–195k", "Referral · Ali"],
    ["Modal", "Design Engineer", "New York", "$165–200k", "Careers page"],
    ["Neon", "Product Designer", "Remote (US)", "$145–175k", "LinkedIn"],
    ["Resend", "Design Engineer", "Remote (global)", "$135–165k", "Twitter"],
    ["Liveblocks", "Frontend Engineer", "Remote (EU)", "€70–90k", "Careers page"],
    ["Mintlify", "Product Designer", "San Francisco", "$150–180k", "Wellfound"],
    ["Warp", "Design Engineer", "Remote (US)", "$160–190k", "Referral · Priya"],
    ["Hex", "Product Designer", "San Francisco", "$155–185k", "LinkedIn"],
    ["Census", "Frontend Engineer", "Remote (US)", "$145–175k", "Careers page"],
    ["Dagster", "Design Engineer", "Remote (US)", "$150–180k", "GitHub"],
    ["Temporal", "Product Designer", "Seattle", "$155–185k", "Recruiter reached out"],
    ["Clerk", "Design Engineer", "Remote (US)", "$150–180k", "Twitter"],
    ["WorkOS", "Frontend Engineer", "Remote (US)", "$155–185k", "Careers page"],
    ["Knock", "Product Designer", "New York", "$145–175k", "LinkedIn"],
    ["Inngest", "Design Engineer", "Remote (global)", "$140–170k", "Careers page"],
    ["Browserbase", "Frontend Engineer", "San Francisco", "$160–190k", "Wellfound"],
    ["Baseten", "Product Designer", "San Francisco", "$155–185k", "Referral · Tom"],
    ["Pinecone", "Design Engineer", "New York", "$165–195k", "LinkedIn"],
    ["Turso", "Frontend Engineer", "Remote (EU)", "€75–95k", "GitHub"],
    ["Xata", "Product Designer", "Remote (EU)", "€72–92k", "Careers page"],
    ["PlanetScale", "Design Engineer", "Remote (US)", "$160–190k", "Twitter"],
    ["Railway", "Frontend Engineer", "Remote (global)", "$140–170k", "Hacker News"],
    ["Vanta", "Product Designer", "San Francisco", "$160–190k", "Recruiter reached out"],
    ["Sentry", "Design Engineer", "San Francisco", "$165–195k", "Careers page"],
    ["Loom", "Product Designer", "Remote (US)", "$150–180k", "LinkedIn"],
    ["Pitch", "Design Engineer", "Berlin", "€78–98k", "Careers page"],
    ["Height", "Product Designer", "Remote (US)", "$145–175k", "Wellfound"],
    ["Sourcegraph", "Frontend Engineer", "Remote (US)", "$155–185k", "Careers page"],
    ["Zed", "Design Engineer", "Remote (US)", "$160–190k", "GitHub"],
    ["Tailscale", "Product Designer", "Remote (global)", "$150–180k", "Referral · Sam"],
    ["Arc", "Design Engineer", "New York", "$160–190k", "Twitter"],
    ["Replit", "Product Designer", "San Francisco", "$155–185k", "Careers page"],
  ];

  const mono: [string, string][] = [
    ["#ede8e8", "#574747"], ["#e7f0ea", "#2f6b46"], ["#eceaf3", "#5b4b86"],
    ["#f1ece4", "#8a5a1f"], ["#e7eef2", "#2f5d72"], ["#f2e9ea", "#86304a"],
    ["#eef1e6", "#566b2f"], ["#efe9e9", "#6b4a4a"],
  ];

  const plan: Record<string, number> = { saved: 6, applied: 18, phone: 8, onsite: 6, offer: 2, rejected: 5 };
  const firstNames = ["Dana", "Wes", "Priya", "Tom", "Sam", "Ali", "Jordan", "Maya", "Chris", "Lena", "Noah", "Iris"];
  const recruiterRoles = ["Recruiter", "Hiring manager", "Design lead", "Talent partner", "Eng manager"];
  const pick = <T,>(arr: T[], i: number): T => arr[i % arr.length];

  const apps: Application[] = [];
  let idx = 0;

  for (const st of STAGES) {
    const n = plan[st.id];
    for (let k = 0; k < n; k++) {
      const s = seeds[idx % seeds.length];
      const [company, role, location, salary, source] = s;
      const c = mono[idx % mono.length];

      const appliedDaysAgo = st.id === "saved" ? null : 3 + ((idx * 7 + k * 5) % 46);
      const updatedDaysAgo = st.id === "saved" ? idx % 9 : (idx * 3 + k * 2) % 19;

      const events: TimelineEvent[] = [];
      const contacts: Contact[] = [];
      const notes: Note[] = [];
      let nextAction: NextAction | null = null;
      let hasDraft = false;

      if (st.id !== "saved") {
        events.push({ daysAgo: appliedDaysAgo as number, kind: "applied", text: "Applied" });
      } else {
        events.push({ daysAgo: updatedDaysAgo, kind: "saved", text: "Saved this role" });
      }

      if (st.id === "phone" || st.id === "onsite" || st.id === "offer") {
        const reply = Math.max(1, (appliedDaysAgo as number) - (4 + (k % 6)));
        events.push({ daysAgo: reply, kind: "reply", text: "Recruiter replied" });
        contacts.push({ name: pick(firstNames, idx), role: "Recruiter", initials: pick(firstNames, idx).slice(0, 1) });
      }
      if (st.id === "onsite" || st.id === "offer") {
        const screen = Math.max(1, (appliedDaysAgo as number) - (10 + (k % 4)));
        events.push({ daysAgo: screen, kind: "screen", text: "Phone screen — went well" });
        contacts.push({ name: pick(firstNames, idx + 3), role: pick(recruiterRoles, idx + 1), initials: pick(firstNames, idx + 3).slice(0, 1) });
      }
      if (st.id === "offer") {
        events.push({ daysAgo: Math.max(1, updatedDaysAgo + 1), kind: "onsite", text: "Onsite — strong fit" });
        events.push({ daysAgo: updatedDaysAgo, kind: "offer", text: "Offer received" });
      }
      if (st.id === "rejected") {
        const got = Math.max(1, (appliedDaysAgo || 10) - (6 + (k % 8)));
        if (k % 2 === 0) events.push({ daysAgo: got + 4, kind: "reply", text: "Recruiter replied" });
        events.push({ daysAgo: updatedDaysAgo, kind: "rejected", text: k % 3 === 0 ? "No longer moving forward" : "Position filled" });
      }

      if (idx % 3 === 0 && st.id !== "saved") {
        const noteText = pick([
          "Team seems small and senior. Ask about design org size.",
          "Comp band looked flexible. They mentioned equity refresh.",
          "Used their product for a year — lead with that.",
          "Referral said the hiring bar is high on craft. Bring the case study.",
          "Remote but quarterly onsites in SF. Confirm travel cadence.",
        ], idx);
        notes.push({ daysAgo: Math.max(0, updatedDaysAgo - 1), text: noteText });
      }

      if (st.id === "saved") {
        nextAction = k % 2 === 0 ? { kind: "apply", label: "Apply", due: k % 4 } : null;
        if (k % 3 === 1) hasDraft = true;
      } else if (st.id === "applied") {
        const dues: (number | null)[] = [-3, 0, 1, 5, -1, 8, 0, 11, 3, -2, 6, null, 1, 9, 0, 4, -1, 7];
        const due = dues[k % dues.length];
        if (due === null) {
          nextAction = { kind: "wait", label: "Waiting to hear back", due: null };
        } else {
          nextAction = { kind: "followup", label: "Send follow-up", due };
          if (due <= 1) hasDraft = k % 2 === 0;
        }
      } else if (st.id === "phone") {
        const dues = [0, 2, -1, 1, 3, 0, 4, 1];
        const due = dues[k % dues.length];
        nextAction = k % 2 === 0
          ? { kind: "interview", label: "Recruiter call", due, time: pick(["10:00", "13:30", "15:00", "11:30"], idx) }
          : { kind: "prep", label: "Prep screening notes", due };
        if (k % 3 === 0) hasDraft = false;
      } else if (st.id === "onsite") {
        const dues = [1, 0, 3, 2, 4, 1];
        const due = dues[k % dues.length];
        nextAction = k % 2 === 0
          ? { kind: "interview", label: "Onsite interview", due, time: pick(["09:30", "13:00", "14:30"], idx) }
          : { kind: "thanks", label: "Send thank-you note", due: 0 };
        if (nextAction.kind === "thanks") hasDraft = k % 2 === 1;
      } else if (st.id === "offer") {
        nextAction = { kind: "offer", label: "Respond to offer", due: k === 0 ? 2 : 5, deadline: k === 0 ? 2 : 5 };
      } else {
        nextAction = null;
      }

      apps.push({
        id: "app-" + (idx + 1),
        company, role, location, salary, source,
        appliedDaysAgo,
        updatedDaysAgo,
        stage: st.id,
        nextAction,
        hasDraft,
        events: events.sort((a, b) => a.daysAgo - b.daysAgo),
        contacts,
        notes,
        mono: { bg: c[0], fg: c[1] },
        starred: idx % 9 === 0,
        stale: false,
      });
      idx++;
    }
  }

  apps.forEach((a) => {
    const active = a.stage === "applied" || a.stage === "phone" || a.stage === "onsite";
    const imminent = !!(a.nextAction && a.nextAction.due !== null && a.nextAction.due <= 3);
    a.stale = active && !imminent && a.updatedDaysAgo >= 11;
  });

  return apps;
}
