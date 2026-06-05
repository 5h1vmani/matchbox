/* Matchbox — Discovery sample data. Roles the system surfaces for triage.
   The student: US-based product designer / design engineer, ~5 yrs, React +
   design systems, no EU work authorization, open to remote. That profile drives
   the fit + eligibility reads below. Hand-authored for honest, specific reasons.
   Exposed as window.ROLES and window.WATCH. */
(function () {
  const mono = {
    Linear: ["#eceaf3", "#5b4b86"], Vercel: ["#18181b", "#fafafa"], Figma: ["#f1ece4", "#8a5a1f"],
    Raycast: ["#f2e7e7", "#9a3b3b"], Stripe: ["#eceaf3", "#5b4b86"], Pitch: ["#1c1c1f", "#fafafa"],
    Supabase: ["#e3efe7", "#2f6b46"], Notion: ["#ededed", "#37352f"], "Cal.com": ["#e7eef2", "#2f5d72"],
    Liveblocks: ["#ede8e8", "#574747"], Ramp: ["#f0ece2", "#7a5c1f"], Retool: ["#e7eef2", "#2f5d72"],
    Replit: ["#f1ece4", "#8a5a1f"], Resend: ["#1c1c1f", "#fafafa"], Tailscale: ["#1c1c1f", "#fafafa"],
    Arc: ["#f2e7ee", "#86304a"], Modal: ["#e7f0ea", "#2f6b46"], Pinecone: ["#e7eef2", "#2f5d72"],
    Xata: ["#ede8e8", "#574747"], Sentry: ["#eceaf3", "#5b4b86"], Loom: ["#eceaf3", "#5b4b86"],
    Warp: ["#1c1c1f", "#fafafa"], Browserbase: ["#f1ece4", "#8a5a1f"], Knock: ["#f2e7ee", "#86304a"],
  };
  const m = (co) => { const x = mono[co] || ["#ede8e8", "#574747"]; return { bg: x[0], fg: x[1] }; };

  // r(company, title, location, remote, salary, source, postedDaysAgo, fitLevel, fitReason,
  //   elig, eligReason, fresh, closingInDays, covered, total)
  let _id = 0;
  function r(company, title, location, remote, salary, source, posted, fitLevel, fitReason, elig, eligReason, fresh, closing, covered, total) {
    _id++;
    return {
      id: "role-" + _id, company, title, location, remote, salary, source,
      postedDaysAgo: posted, link: "#",
      fit: { level: fitLevel, reason: fitReason },
      eligibility: { status: elig, reason: eligReason },
      freshness: fresh, closingInDays: closing == null ? null : closing,
      coverage: total ? { covered, total } : null,
      mono: m(company),
      jd: JD[company] || JD._default,
      decision: null, // null | 'tracked' | 'dismissed' | 'tailoring'
    };
  }

  const JD = {
    _default: [
      "We're a small, senior team building tools developers love. You'll own design end to end, from first sketch to shipped pixels, working closely with engineering.",
      "What you'll do: lead design on core product areas, contribute to and maintain our design system, prototype in code where it helps, and partner with founders on product direction.",
      "What we're looking for: 4+ years designing software products, a portfolio that shows craft and systems thinking, comfort working in ambiguity, and a bias for shipping.",
      "Nice to have: experience with developer tools, ability to build your own prototypes in React, and a track record of design-system work.",
    ],
    Linear: [
      "Linear helps teams move faster with a purpose-built tool for planning and building products. Design is core to everything we do.",
      "As a Senior Product Designer you'll own major surfaces of the product, set the bar for craft, and extend the design system that makes Linear feel like Linear.",
      "We're looking for someone with 5+ years of product design experience, deep systems thinking, and an obsession with the details. You should be comfortable shipping quickly and iterating in the open.",
      "Must-haves: end-to-end product design, design-system fluency, strong interaction design, and the ability to communicate decisions clearly. Bonus: you can prototype in code.",
    ],
    Vercel: [
      "Vercel is the platform for frontend developers. We're hiring a Design Engineer to sit at the seam of design and engineering.",
      "You'll turn design intent into production React, build and maintain component libraries, and raise the quality bar across the product.",
      "We want someone who designs and codes: strong Figma skills, fluent in React and TypeScript, and a real eye for motion and detail.",
    ],
  };

  const ROLES = [
    r("Linear", "Senior Product Designer", "Remote", true, "$150–185k", "Referral · Dana", 2, "strong", "Your 5 years and design-systems work map almost exactly to what they need.", "eligible", "Remote US. No visa or relocation needed.", "open", null, 7, 9),
    r("Vercel", "Design Engineer", "Remote", true, "$160–190k", "Careers page", 1, "strong", "They want a designer who ships React. That's your exact shape.", "eligible", "Hires remote in the US.", "open", null, 8, 9),
    r("Resend", "Design Engineer", "Remote", true, "$135–165k", "Twitter", 2, "strong", "Small team, design-and-eng hybrid role. Your sweet spot.", "eligible", "Remote, global.", "open", null, 8, 9),
    r("Warp", "Design Engineer", "Remote", true, "$160–190k", "Referral · Priya", 2, "strong", "Terminal-grade craft and a referral already in the door.", "eligible", "Remote US.", "open", null, 8, 9),
    r("Notion", "Design Engineer", "San Francisco", false, "$165–195k", "Referral · Wes", 8, "strong", "Systems-heavy role, and Wes can put your name forward.", "eligible", "SF onsite, you're in the US.", "closing", 2, 8, 9),
    r("Retool", "UX Engineer", "Remote", true, "$150–180k", "Careers page", 3, "strong", "Internal-tools UX rewards systems thinkers like you.", "eligible", "Remote US.", "open", null, 7, 9),
    r("Stripe", "Sr. Product Designer", "New York", false, "$170–210k", "LinkedIn", 6, "good", "Strong overall match; their bar on visual polish is high.", "eligible", "NY onsite, you're eligible.", "closing", 3, 7, 9),
    r("Tailscale", "Product Designer", "Remote", true, "$150–180k", "Referral · Sam", 5, "good", "Networking product, but the design problems are squarely yours.", "eligible", "Remote, global.", "open", null, 7, 9),
    r("Cal.com", "Design Engineer", "Remote", true, "$130–160k", "GitHub", 1, "good", "Open-source scheduling. Design-eng hybrid, slightly junior of you.", "eligible", "Remote, global.", "open", null, 6, 8),
    r("Sentry", "Design Engineer", "San Francisco", false, "$165–195k", "Careers page", 4, "good", "Mature product, lots of surface area. Solid fit.", "eligible", "SF onsite, US.", "open", null, 7, 10),
    r("Arc", "Design Engineer", "New York", false, "$160–190k", "Twitter", 6, "good", "Browser craft is detail-heavy, which plays to your strengths.", "eligible", "NY onsite, US.", "open", null, 6, 9),
    r("Knock", "Product Designer", "New York", false, "$145–175k", "LinkedIn", 7, "good", "Notifications infra. Clear problems, smaller design team.", "eligible", "NY onsite, US.", "open", null, 6, 9),
    r("Figma", "Staff Product Designer", "San Francisco", false, "$190–230k", "Recruiter reached out", 4, "stretch", "Staff is a level up from where you are now, but your craft is close.", "eligible", "SF onsite, US.", "open", null, 6, 10),
    r("Ramp", "Product Design Lead", "New York", false, "$185–220k", "LinkedIn", 7, "stretch", "A lead role means managing, which is a step beyond your track so far.", "eligible", "NY onsite, US.", "open", null, 6, 10),
    r("Modal", "Design Engineer", "New York", false, "$165–200k", "Careers page", 1, "stretch", "Infra-heavy product with a real learning curve on the domain.", "eligible", "NY onsite, US.", "open", null, 5, 9),
    r("Pinecone", "Design Engineer", "New York", false, "$165–195k", "LinkedIn", 9, "stretch", "Vector databases are far from your past work; expect a ramp.", "eligible", "NY onsite, US.", "closing", 5, 5, 9),
    r("Browserbase", "Frontend Engineer", "San Francisco", false, "$160–190k", "Wellfound", 1, "stretch", "Leans more frontend-eng than design.", "unclear", "They may want more backend depth than your CV shows. Worth a closer look.", "open", null, 5, 9),
    r("Supabase", "Frontend Engineer", "Remote", true, "$140–170k", "Careers page", 2, "stretch", "More engineering than design. Some backend gaps.", "unclear", "Role mixes frontend and some Postgres work. Check if that's a dealbreaker.", "open", null, 5, 10),
    // ineligible — set aside (honest, kind)
    r("Raycast", "Product Designer", "Remote", true, "€75–95k", "Twitter", 3, "good", "Product sense matches well.", "ineligible", "EU-only contract. You'd need EU work authorization.", "open", null, null, null),
    r("Liveblocks", "Frontend Engineer", "Remote", true, "€70–90k", "Careers page", 4, "good", "Collaborative-editing tech, interesting problems.", "ineligible", "EU-based applicants only.", "open", null, null, null),
    r("Xata", "Product Designer", "Remote", true, "€72–92k", "Careers page", 3, "good", "Database UX, squarely designable.", "ineligible", "EU remote only.", "open", null, null, null),
    r("Pitch", "Design Engineer", "Berlin", false, "€78–98k", "Careers page", 5, "good", "Presentation software, lots of polish.", "ineligible", "Berlin onsite. Needs a German or EU work permit.", "open", null, null, null),
    // closed
    r("Replit", "Product Designer", "San Francisco", false, "$155–185k", "Careers page", 14, "good", "Would have been a strong match.", "eligible", "SF onsite, US.", "closed", null, null, null),
    r("Loom", "Product Designer", "Remote", true, "$150–180k", "LinkedIn", 12, "good", "Video-first product, good problems.", "eligible", "Remote US.", "closed", null, null, null),
  ];

  // companies worth watching even with no role today
  const WATCH = [
    { company: "Anthropic", note: "No open design roles right now. They opened 3 in the last year.", status: "watching", openRoles: 0, mono: { bg: "#f1ece4", fg: "#8a5a1f" } },
    { company: "Raycast", note: "EU-only so far. Watching for a US-eligible opening.", status: "watching", openRoles: 1, mono: m("Raycast") },
    { company: "Linear", note: "You're reviewing 1 open role from them today.", status: "active", openRoles: 1, mono: m("Linear") },
    { company: "Vercel", note: "Strong culture fit. Reviewing 1 role now.", status: "active", openRoles: 1, mono: m("Vercel") },
    { company: "Superhuman", note: "No openings now. High craft bar, worth the wait.", status: "watching", openRoles: 0, mono: { bg: "#eceaf3", fg: "#5b4b86" } },
    { company: "Mintlify", note: "Hired recently. Check back next quarter.", status: "watching", openRoles: 0, mono: { bg: "#e7f0ea", fg: "#2f6b46" } },
  ];

  window.ROLES = ROLES;
  window.WATCH = WATCH;
})();
