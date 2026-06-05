/* Matchbox — Studio sample data. One connected story so all seven surfaces feel
   like one product: Maya Chen, a product designer, building her fact pool, tailoring
   for Linear, prepping, and weighing Linear vs Stripe offers.
   Local-first, multi-profile. Exposed on window.STUDIO. */
(function () {
  // ---- profiles (switch people on one machine, no accounts) ----
  const profiles = [
    { id: "maya", name: "Maya Chen", initials: "MC", color: "#574747", file: "maya-chen.matchbox", active: true },
    { id: "dev", name: "Dev Patel", initials: "DP", color: "#2f5d72", file: "dev-patel.matchbox" },
    { id: "sara", name: "Sara Lind", initials: "SL", color: "#2f6b46", file: "sara-lind.matchbox" },
  ];

  // ---- the fact pool / library: verified reusable sentences ----
  // status: verified (corroborated by an uploaded doc), thin (weak/vague/one source), gap (assistant wants evidence)
  const facts = [
    { id: "f1", cat: "Impact", text: "Led the redesign of Acme's checkout flow, lifting completed purchases by 23% in the first quarter.", status: "verified", sources: ["Resume_2024.pdf", "Pasted story"], metric: true, usedIn: 4 },
    { id: "f2", cat: "Experience", text: "Owned the design system at Acme end to end, from tokens to a 40-component React library used by 6 product teams.", status: "verified", sources: ["Resume_2024.pdf", "LinkedIn export"], metric: true, usedIn: 7 },
    { id: "f3", cat: "Impact", text: "Cut onboarding drop-off by a third by rebuilding the first-run experience around a single clear action.", status: "verified", sources: ["Pasted story"], metric: true, usedIn: 2 },
    { id: "f4", cat: "Skill", text: "Prototype in React and TypeScript, shipping production-quality front-end for the flows I design.", status: "verified", sources: ["Resume_2024.pdf", "GitHub"], metric: false, usedIn: 5 },
    { id: "f5", cat: "Experience", text: "Designed and shipped Acme's mobile app from zero to launch, reaching 50k installs in six months.", status: "verified", sources: ["Resume_2024.pdf"], metric: true, usedIn: 3 },
    { id: "f6", cat: "Skill", text: "Run end-to-end research, from interviews to usability tests, and turn findings into shipped changes.", status: "thin", sources: ["LinkedIn export"], metric: false, usedIn: 1, note: "Only on LinkedIn, no specifics. Add an example to make it land." },
    { id: "f7", cat: "Experience", text: "Mentored two junior designers, both promoted within a year.", status: "thin", sources: ["Pasted story"], metric: true, usedIn: 0, note: "One source. A document mention would verify it." },
    { id: "f8", cat: "Education", text: "BFA in Interaction Design, California College of the Arts, 2017.", status: "verified", sources: ["Resume_2024.pdf", "LinkedIn export"], metric: false, usedIn: 6 },
    { id: "f9", cat: "Skill", text: "Comfortable leading design critique and setting craft standards across a team.", status: "thin", sources: ["LinkedIn export"], metric: false, usedIn: 0, note: "Vague. Tie it to a moment where you set the bar." },
  ];

  // gaps the assistant is asking Maya to fill (specific, answerable)
  const gaps = [
    { id: "g1", prompt: "You mention leading a redesign. Roughly how big was the team you led?", why: "Linear and similar roles ask about leadership scope. A number here strengthens 3 of your bullets.", forFact: "f1" },
    { id: "g2", prompt: "Do you have a measurable result for the research work, or a project where research changed the outcome?", why: "Turns a thin skill into a verified, specific claim.", forFact: "f6" },
    { id: "g3", prompt: "Any management or mentorship you can point to in a document (review, offer letter, deck)?", why: "Several senior roles weigh this. Right now it rests on one story.", forFact: "f7" },
  ];

  // intake sources (uploaded / pasted raw material)
  const intake = [
    { id: "s1", kind: "cv", label: "Resume_2024.pdf", meta: "Uploaded 2 days ago · 14 facts extracted", status: "processed", icon: "file-text" },
    { id: "s2", kind: "linkedin", label: "LinkedIn export", meta: "Imported · 9 roles, 22 skills", status: "processed", icon: "linkedin" },
    { id: "s3", kind: "cv", label: "Resume_2021_old.pdf", meta: "Uploaded · 8 facts, 5 already known", status: "processed", icon: "file-text" },
    { id: "s4", kind: "story", label: "Pasted stories", meta: "3 stories · added by you", status: "processed", icon: "pen-line" },
    { id: "s5", kind: "cv", label: "Portfolio_casestudy.pdf", meta: "Reading now…", status: "working", icon: "file-text" },
  ];

  const completeness = {
    verified: facts.filter((f) => f.status === "verified").length,
    thin: facts.filter((f) => f.status === "thin").length,
    gaps: gaps.length,
    total: facts.length,
    // coverage by area
    areas: [
      { area: "Impact & results", level: "strong", note: "3 results with numbers" },
      { area: "Craft & skills", level: "strong", note: "well evidenced" },
      { area: "Leadership", level: "thin", note: "rests on one story" },
      { area: "Research", level: "thin", note: "no specific example yet" },
    ],
  };

  // ---- search & sources setup (where to look) ----
  const searchSources = [
    { id: "src1", name: "LinkedIn Jobs", on: true, kind: "board", note: "Roles matching your titles and locations" },
    { id: "src2", name: "Wellfound (AngelList)", on: true, kind: "board", note: "Startup roles" },
    { id: "src3", name: "Company career pages", on: true, kind: "board", note: "12 companies on your watchlist" },
    { id: "src4", name: "Hacker News \u2018Who is hiring\u2019", on: false, kind: "board", note: "Monthly thread, remote-friendly" },
    { id: "src5", name: "Otta", on: false, kind: "board", note: "Curated tech roles" },
  ];
  const searchPrefs = {
    titles: ["Product Designer", "Senior Product Designer", "Design Engineer"],
    locations: ["Remote (US)", "San Francisco", "New York"],
    minSalary: "150",
    seniority: "Senior",
  };

  // ---- tailoring review (screen 3): the highest-stakes diff + coverage ----
  const tailoring = {
    role: { company: "Linear", title: "Senior Product Designer", mono: { bg: "#eceaf3", fg: "#5b4b86" }, location: "Remote (US)", salary: "$150\u2013185k" },
    summary: { changed: 5, kept: 3, added: 2, requirementsCovered: 9, requirementsTotal: 12, gapsLeft: 3 },
    // requirements pulled from the JD, each mapped to evidence (or honestly empty)
    requirements: [
      { id: "r1", text: "5+ years of product design experience", status: "covered", evidence: "f2", how: "Backed by your Acme design-system tenure" },
      { id: "r2", text: "Deep design-systems fluency", status: "covered", evidence: "f2", how: "Directly evidenced" },
      { id: "r3", text: "Ships production front-end / prototypes in code", status: "covered", evidence: "f4", how: "React + TypeScript fact" },
      { id: "r4", text: "Strong interaction design and craft", status: "covered", evidence: "f1", how: "Checkout redesign result" },
      { id: "r5", text: "End-to-end ownership, zero to one", status: "covered", evidence: "f5", how: "Mobile app launch" },
      { id: "r6", text: "Measurable product impact", status: "covered", evidence: "f3", how: "Onboarding drop-off result" },
      { id: "r7", text: "Clear communicator of design decisions", status: "covered", evidence: "f2", how: "Implied by cross-team system work" },
      { id: "r8", text: "Comfort in ambiguity / fast iteration", status: "partial", evidence: null, how: "Implied, but no direct evidence in your library" },
      { id: "r9", text: "Sets craft standards across a team", status: "partial", evidence: "f9", how: "You say this, but it's a thin (unverified) claim" },
      { id: "r10", text: "Leads and mentors other designers", status: "empty", evidence: null, how: "Only one unverified story. We left this out rather than overstate it." },
      { id: "r11", text: "Experience with developer tools / technical users", status: "empty", evidence: null, how: "Nothing in your library speaks to this. Left empty." },
      { id: "r12", text: "Has used Linear day to day", status: "empty", evidence: null, how: "We can't claim this for you. Left empty." },
    ],
    // the CV diff: each line is unchanged / rephrased (from a verified source) / added (from a verified source)
    diff: [
      { id: "d1", kind: "rephrased", source: "f1",
        before: "Redesigned the checkout and improved conversion.",
        after: "Led the checkout-flow redesign that lifted completed purchases 23% in one quarter, the kind of measurable craft Linear hires for.",
        note: "Rephrased to foreground the metric and tie it to the role. Same fact, your words." },
      { id: "d2", kind: "rephrased", source: "f2",
        before: "Worked on the design system.",
        after: "Owned Acme's design system end to end, a 40-component React library used by 6 teams.",
        note: "Sharpened from your verified fact. Nothing added." },
      { id: "d3", kind: "kept", source: "f5",
        after: "Designed and shipped Acme's mobile app from zero to launch, 50k installs in six months.",
        note: "Already strong and relevant. Left as-is." },
      { id: "d4", kind: "added", source: "f4",
        after: "Prototype in React and TypeScript, shipping production front-end for the flows I design.",
        note: "Added because Linear explicitly wants designers who code. Pulled from your verified library, not invented." },
      { id: "d5", kind: "rephrased", source: "f3",
        before: "Improved onboarding.",
        after: "Rebuilt the first-run experience around one clear action, cutting onboarding drop-off by a third.",
        note: "Made the result concrete from your verified fact." },
      { id: "d6", kind: "added", source: "f8",
        after: "BFA in Interaction Design, California College of the Arts.",
        note: "Standard, verified. Added for completeness." },
      { id: "d7", kind: "kept", source: "f7", flag: true,
        after: "Mentored two junior designers, both promoted within a year.",
        note: "Kept, but flagged: this is a thin claim. Verify it in your Library before you lean on it in interviews." },
    ],
  };

  // ---- application workspace (screen 4) ----
  const workspace = {
    company: "Stripe", title: "Sr. Product Designer", mono: { bg: "#eceaf3", fg: "#5b4b86" },
    stage: "Onsite", nextDate: "Thu, 2:00pm",
    prep: {
      generatedDaysAgo: 1,
      about: "Stripe builds economic infrastructure for the internet. The design org is large and craft-led; this role sits on the Payments surface, which is dense, high-trust, and detail-obsessed.",
      questions: [
        { q: "Walk us through a time you simplified a genuinely complex flow.", hint: "Lead with the checkout redesign. The 23% is your anchor." },
        { q: "How do you work with engineers on a shared system?", hint: "Your 40-component library used by 6 teams is the story." },
        { q: "How do you handle a disagreement with a PM on priority?", hint: "Have a concrete example ready. This is a values probe." },
      ],
      talking: ["Checkout redesign, 23% lift", "Design system across 6 teams", "You prototype in code (rare, they value it)"],
      watch: ["Payments is regulated, expect questions on edge cases and error states", "They'll probe depth, not breadth. Go deep on one project."],
    },
    drafts: [
      { id: "w1", kind: "thanks", title: "Thank-you note", timing: "Send within 24h of the onsite", status: "draft",
        body: "Hi Dana,\n\nThank you for the time today. I especially enjoyed digging into how the Payments team balances trust and speed. It is exactly the kind of dense, high-stakes design I want to be doing.\n\nOur conversation about error states stuck with me; I have been sketching a few ideas since.\n\nBest,\nMaya" },
      { id: "w2", kind: "followup", title: "Follow-up", timing: "Send in 5 days if you have not heard back", status: "scheduled",
        body: "Hi Dana,\n\nJust following up on Thursday's onsite. I remain very excited about the Payments role and would love to know about next steps whenever the team has had a chance to regroup.\n\nThanks again,\nMaya" },
    ],
  };

  // ---- offer & negotiation (screen 5) ----
  const offers = {
    deadline: "Linear offer expires in 4 days",
    // user's own priorities, weighted (they set these)
    priorities: [
      { id: "comp", label: "Compensation", weight: 4 },
      { id: "growth", label: "Growth & scope", weight: 5 },
      { id: "remote", label: "Remote / flexibility", weight: 5 },
      { id: "team", label: "Team & craft", weight: 4 },
      { id: "mission", label: "Mission fit", weight: 3 },
    ],
    competing: [
      { id: "o1", company: "Linear", role: "Senior Product Designer", mono: { bg: "#eceaf3", fg: "#5b4b86" },
        base: 178000, bonus: 0, equityNote: "0.08% over 4 years", remote: "Fully remote", note: "Smaller team, more scope",
        scores: { comp: 4, growth: 5, remote: 5, team: 5, mission: 4 } },
      { id: "o2", company: "Stripe", role: "Sr. Product Designer", mono: { bg: "#eceaf3", fg: "#5b4b86" },
        base: 195000, bonus: 25000, equityNote: "RSUs ~$60k/yr", remote: "Hybrid, 3 days SF", note: "Bigger comp, less ownership",
        scores: { comp: 5, growth: 3, remote: 2, team: 4, mission: 3 } },
    ],
    // salary context — deliberately honest about confidence (cross-cutting B)
    salaryContext: {
      role: "Senior Product Designer, Remote US",
      range: [165000, 205000],
      median: 184000,
      confidence: "low",
      basis: "Based on 4 self-reported data points from 2023\u201324. Treat as a rough guide, not a benchmark.",
    },
    counter: {
      target: 190000,
      to: "Linear",
      body: "Hi Sam,\n\nThank you so much for the offer. I am genuinely excited about Linear and the scope of this role.\n\nI do want to be straightforward about compensation. Based on what I am seeing for senior remote design roles, and a competing offer with a higher base, I would feel comfortable accepting at a base of $190k. The equity and remote setup already feel right to me.\n\nIs there room to get there? I would love to make this work.\n\nBest,\nMaya",
    },
  };

  // ---- insights (screen 6): funnel + honest calibration ----
  const insights = {
    funnel: [
      { stage: "Applied", n: 24, rate: null },
      { stage: "Replied", n: 11, rate: 46 },
      { stage: "Screen", n: 7, rate: 64 },
      { stage: "Onsite", n: 3, rate: 43 },
      { stage: "Offer", n: 1, rate: 33 },
    ],
    calibration: [
      { metric: "Response rate", value: "46%", n: 24, confidence: "medium", note: "11 of 24 replied. Enough to trust, not a lot.", benchmark: "Typical is 20\u201340%. You're above." },
      { metric: "Screen \u2192 onsite", value: "43%", n: 7, confidence: "low", note: "Only 7 screens so far. Too early to read much into this.", benchmark: "Hard to benchmark this early." },
      { metric: "Offer rate", value: "1 offer", n: 3, confidence: "low", note: "3 onsites, 1 offer. Way too few to call a rate.", benchmark: "Come back after a few more." },
    ],
    note: "You're early. The response rate is starting to mean something; everything past the screen is still too thin to read. Keep going, the numbers will sharpen.",
  };

  // ---- assistant queue (cross-cutting C): calm ambient async state ----
  const assistant = [
    { id: "a1", label: "Tailoring CV for Vercel", kind: "tailor", state: "working", eta: "about a minute" },
    { id: "a2", label: "Drafting follow-up for Notion", kind: "draft", state: "queued", eta: null },
    { id: "a3", label: "Tailored CV for Linear", kind: "tailor", state: "done", at: "2m ago" },
    { id: "a4", label: "Interview prep for Stripe", kind: "prep", state: "done", at: "1h ago" },
  ];

  window.STUDIO = { profiles, facts, gaps, intake, completeness, searchSources, searchPrefs, tailoring, workspace, offers, insights, assistant };
})();
