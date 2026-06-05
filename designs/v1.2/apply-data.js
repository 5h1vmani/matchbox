/* Matchbox — the rest of the journey. Application packet (cover letter +
   screening Q&A + submit), the reusable answer library, people/referrals,
   interview rounds + debrief, and an honest momentum/coach + rejection-learning
   layer. Same Maya → Linear story. Exposed as window.APPLY. */
(function () {
  // ---- the full application packet for Linear ----
  const packet = {
    role: { company: "Linear", title: "Senior Product Designer", mono: { bg: "#eceaf3", fg: "#5b4b86" }, location: "Remote (US)", salary: "$150–185k" },
    coverLetter: {
      status: "draft",
      paragraphs: [
        { id: "p1", source: "your voice", note: "Your genuine reason. We left this for you to confirm, not invent.", confirmed: true,
          text: "I've used Linear every day for two years, and it's the rare tool whose craft makes me want to build for the people who make it. That's why I'm applying." },
        { id: "p2", source: "f2", note: "Built from a verified fact in your library.",
          text: "At Acme I owned the design system end to end, a 40-component React library used by six product teams. I care about systems the way Linear does: as the thing that lets everyone move fast without drift." },
        { id: "p3", source: "f1", note: "Built from a verified fact (the 23% result).",
          text: "I also like to prove craft with outcomes. My redesign of Acme's checkout lifted completed purchases 23% in a quarter, and I prototype in React so the handoff is the real thing, not a picture of it." },
        { id: "p4", source: "your voice", note: "A short, honest close. Edit freely.", confirmed: true,
          text: "I'd love to bring that to your team. Thank you for considering me." },
      ],
    },
    questions: [
      { id: "q1", q: "Why do you want to work at Linear?", answer: "I've used Linear daily for two years and admire how its craft sets the bar for the category. I want to design for a team that treats quality as the product.", source: "answer:a-why", status: "answered", note: "Drafted from your saved answer, tuned to Linear." },
      { id: "q2", q: "What are your salary expectations?", answer: "$170k base, with flexibility on the equity mix.", source: "profile", status: "answered" },
      { id: "q3", q: "Are you authorized to work in the US? Do you need sponsorship?", answer: "US citizen. No sponsorship needed.", source: "profile", status: "answered" },
      { id: "q4", q: "When could you start?", answer: "Four weeks from an offer (standard notice).", source: "profile", status: "answered" },
      { id: "q5", q: "Link to your portfolio", answer: "mayachen.design", source: "profile", status: "answered" },
      { id: "q6", q: "Anything that makes you a uniquely good fit? (optional)", answer: "", source: null, status: "needs-you", note: "Optional. We won't fill this in for you; a sentence in your own words lands better than ours." },
    ],
  };

  // ---- reusable answer library (the questions you answer over and over) ----
  const answers = [
    { id: "a-why", question: "Why do you want to work here?", answer: "I'm drawn to teams that treat craft as the product and move fast without losing quality. I want to do my best work alongside people who care about the details.", kind: "template", status: "verified", usedIn: 6, note: "Template. The assistant tailors the company-specific part each time." },
    { id: "a-weak", question: "What's your biggest weakness?", answer: "I used to hold work too long chasing polish. I've learned to ship at 90% and iterate in the open, which has made me faster and more collaborative.", status: "verified", usedIn: 4 },
    { id: "a-conflict", question: "Tell me about a disagreement with a PM.", answer: "On the checkout project a PM wanted to ship without an error-state pass. I made the risk concrete with a quick prototype of the failure cases, we agreed on a two-day fix, and it caught a bug that would have hit 5% of orders.", status: "verified", usedIn: 3, source: "Pasted story" },
    { id: "a-salary", question: "Salary expectations", answer: "$170k base, flexible on the equity mix depending on the overall package.", status: "verified", usedIn: 9 },
    { id: "a-leaving", question: "Why are you leaving your current role?", answer: "I've shipped the things I set out to at Acme and I'm looking for a smaller, craft-led team where I can own more of the product.", status: "verified", usedIn: 5 },
    { id: "a-5yr", question: "Where do you see yourself in five years?", answer: "Leading design on a product I believe in, ideally one I helped shape from early on, and mentoring a small team.", status: "thin", usedIn: 2, note: "A little generic. Worth making specific to you." },
    { id: "a-strength", question: "What's your greatest strength?", answer: "I bridge design and engineering. I can take a flow from research to a shipped, production-quality front-end, which keeps teams fast and the craft intact.", status: "verified", usedIn: 4 },
  ];

  // ---- people / referrals (the network channel) ----
  const people = [
    { id: "pe1", name: "Dana Wu", role: "Design Lead", company: "Linear", mono: { bg: "#eceaf3", fg: "#5b4b86" }, relationship: "Former colleague at Acme", strength: "strong", lastContact: "3 weeks ago", canRefer: true, status: "warm", note: "Offered to put your name in for the Senior PD role. Worth following up before you apply cold." },
    { id: "pe2", name: "Priya Shah", role: "Recruiter", company: "Warp", mono: { bg: "#1c1c1f", fg: "#fafafa" }, relationship: "Reached out to you", strength: "medium", lastContact: "1 week ago", canRefer: true, status: "active", note: "Already in conversation. Reply about the Design Engineer role." },
    { id: "pe3", name: "Wes Park", role: "Design Engineer", company: "Notion", mono: { bg: "#ededed", fg: "#37352f" }, relationship: "Intro from Dana", strength: "medium", lastContact: "never", canRefer: true, status: "cold", note: "Dana offered to introduce you. You have a role tracked at Notion." },
    { id: "pe4", name: "Sam Ortiz", role: "Hiring Manager", company: "Tailscale", mono: { bg: "#1c1c1f", fg: "#fafafa" }, relationship: "Met at Config 2024", strength: "weak", lastContact: "2 months ago", canRefer: false, status: "cold", note: "Loose connection. A light check-in could warm it up." },
    { id: "pe5", name: "Lena Cho", role: "Senior Designer", company: "Figma", mono: { bg: "#f1ece4", fg: "#8a5a1f" }, relationship: "Design community", strength: "medium", lastContact: "1 month ago", canRefer: true, status: "cold", note: "Could refer you. You have a Staff role tracked at Figma (a stretch)." },
  ];

  // companies in your pipeline where you already know someone
  const warmPaths = [
    { company: "Linear", who: "Dana Wu", how: "Former colleague, offered to refer", peId: "pe1" },
    { company: "Notion", who: "Wes Park", how: "Intro available via Dana", peId: "pe3" },
    { company: "Figma", who: "Lena Cho", how: "Could refer you", peId: "pe5" },
  ];

  const introDraft = {
    to: "Dana Wu",
    subject: "Linear Senior PD — would love your help",
    body: "Hi Dana,\n\nHope you're well! I saw Linear is hiring a Senior Product Designer and it looks like a great fit for me. You mentioned a while back you'd be happy to refer me. Would you still be up for it?\n\nI've attached the short version of why I think I'd be a fit. No worries at all if the timing isn't right.\n\nThanks so much,\nMaya",
  };

  // ---- interview loop (rounds + debrief) for the Stripe application ----
  const rounds = [
    { id: "rd1", label: "Recruiter screen", who: "Dana Lee", role: "Recruiter", when: "Done · last week", status: "done", focus: "Background, motivation, logistics",
      debrief: { went: "well", asked: ["Why Stripe?", "Salary expectations", "Notice period"], notes: "Warm. She liked the checkout story and flagged the team cares about error states." } },
    { id: "rd2", label: "Hiring manager", who: "Sam Okafor", role: "Design Manager, Payments", when: "Done · 2 days ago", status: "done", focus: "Craft depth, systems thinking", debrief: null },
    { id: "rd3", label: "Onsite loop", who: "4 interviewers", role: "Portfolio · App critique · Systems · Values", when: "Thu, 2:00pm", status: "upcoming", focus: "Go deep on one project; expect regulated-edge-case questions" },
    { id: "rd4", label: "Team & values", who: "Jordan Ellis", role: "Director of Design", when: "Not scheduled", status: "pending", focus: "Culture, long-term fit" },
  ];

  // ---- honest momentum / coach ----
  const momentum = {
    thisWeek: { applied: 6, interviews: 2, followups: 4 },
    target: 5,
    pace: "good", // good | push | rest
    headline: "You're at a strong, sustainable pace.",
    message: "6 applications and 2 interviews this week. That's plenty. Rest this weekend without guilt; the pipeline is healthy.",
    reframes: [
      "You reached onsite in 3 of your 5 most active pipelines. For senior design roles, that's working.",
      "Your response rate (46%) is above the typical 20–40%. Companies are interested.",
    ],
  };

  // ---- learning from rejection (close-the-loop patterns) ----
  const patterns = {
    closed: 5,
    reasons: [
      { reason: "Went with internal / referral", count: 2, tone: "neutral" },
      { reason: "Comp was below your floor", count: 1, tone: "neutral" },
      { reason: "No response (ghosted)", count: 1, tone: "neutral" },
      { reason: "Role paused / filled", count: 1, tone: "neutral" },
    ],
    insight: "None of your 5 closed roles fell apart on craft. The misses were timing, comp, and referrals beating cold applies, which is exactly why working your network matters more than volume right now.",
    nudge: "You know someone at 3 companies in your pipeline. Warm paths convert far better than cold ones.",
  };

  window.APPLY = { packet, answers, people, warmPaths, introDraft, rounds, momentum, patterns };
})();
