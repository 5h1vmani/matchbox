# Canonical Cover Letter — DRAFT for Shiva Padakanti

**Purpose:** the 80% fallback cover letter used for tier-3 and tier-4 applications.
**Format:** markdown draft (converts to Typst in Phase 3 of v0.2).
**Length target:** under 250 words, fits 1 page.
**Voice:** verified against voice rules.
**Status:** DRAFT v2 (2026-04-21) — Shiva reviews and edits.

## Geo variants (render strategy)

Same 3-variant approach as the canonical CV:

- **`cover-canonical-uk.pdf`** — for UK-based roles. Includes a brief UK-history line in the opening paragraph.
- **`cover-canonical-india.pdf`** — for India-based roles. No relocation mention.
- **`cover-canonical-relocate.pdf`** — for all other geographies. Includes "I am happy to relocate" in the opening.

All three pre-rendered once via `matchbox rebuild-canonicals --profile shiva`, cached at `people/shiva/cover-canonical-{geo}.pdf`, copied at submission time by the tier-3/4 tailor path.

---

Dear hiring team,

In August 2025 I met an optometrist in Hyderabad who told me she could not afford to dream bigger than optometry for her son. That conversation started Vidhar, and two months later I shipped Pinaka, an exam-prep platform for NEET droppers, as a solo founder. It is load-tested to 250,000 concurrent users on AWS serverless. I ship AI-native systems with Claude Code as my daily collaborator, and I am looking for a role where that craft serves a team's customers instead of only my own. `{{GEO_OPENING_LINE}}`

Before Vidhar, I spent six years in the UK. Three years at Deltabase producing 42 financial and commercial due diligence reports with AI-assisted synthesis, cutting research time 58 to 60 percent before that was the industry default. Two years at NTT DATA London training 150+ finance analysts across 30 European entities to replace Excel-based reporting with SAP Analytics Cloud. Five months ago I had never shipped production code. Since then I have shipped Pinaka, Matchbox (a personal AI job pipeline with SQLite as its single source of truth and a Streamlit review UI), Bodhi (an open-source MCP server on npm), Kubera (a business-idea validation framework), and Usepaso (a YAML-first MCP tool generator on npm and PyPI).

I am looking for work that pairs real customer exposure with AI-native shipping. I bring enterprise-scale stakeholder experience, five months of production building in the AI-native stack, and a founder-shipper posture that carries across contexts. Where others write speculative code, I would rather spend a week understanding the customer's workflow first.

Happy to talk further,
Shiva Padakanti

## Geo-parameterized line substitution

The `{{GEO_OPENING_LINE}}` placeholder above is replaced at render time by ONE of:

- **If `geo == "uk"`:** "I have six years of UK work history through a Tier 2 visa, and am available for London-based or UK-remote roles without sponsorship constraints."
- **If `geo == "india"`:** (empty — no line added; the sentence before flows straight to paragraph 2)
- **If `geo == "relocate"`:** "I am happy to relocate for the right role."

Phase 3 Typst template handles the substitution deterministically. Pre-rendered variants produced: `cover-canonical-uk.pdf`, `cover-canonical-india.pdf`, `cover-canonical-relocate.pdf`.

---

**Word count:** approximately 230 words. Fits one page at 11pt with spacing.

**Draft notes for Shiva to review (v2, 2026-04-21):**

1. **Geo-parameterized line added** in P1. See the substitution table above. Renders as 3 pre-rendered variants (UK, India, Relocate).

2. **P2 project list updated** — now lists 5 projects (Pinaka, Matchbox, Bodhi, Kubera, Usepaso). Vasapitta excluded from canonical.

3. **Salutation:** "Dear hiring team" is generic. For bespoke covers (tier-1) this becomes "Dear [specific person]" or "Dear [team name]". For canonical, generic is correct.

4. **Opener:** "In August 2025 I met an optometrist in Hyderabad" — the Five-Percent Problem story. Pattern-break, emotionally resonant. Tradeoff: anchors the cover to the NEET-dropper origin which may not land for all readers. Alternative: "Five months ago I had never shipped production code. Today I have shipped five tools." Say if you want the swap.

5. **Costly signal** ("Five months ago I had never shipped production code") kept in P2. Strong, defensible.

6. **Factual anchors in P2:** 6 years UK, 3 years Deltabase + 42 reports + 58-60% savings, 2 years NTT DATA + 150+ users + 30 entities, 5 months production, 5 shipped tools. Dense. Verifiable.

7. **P3 closing:** deliberately generic-forward-looking. For bespoke letters we swap with a specific company-and-role anchor. For canonical, the "I would rather spend a week understanding the customer's workflow" line is the differentiator.

8. **Sign-off:** "Happy to talk further" is warm, not sycophantic. Alternatives: "Thank you for considering this application" (formal) or "Looking forward to the conversation" (assertive). Current is my pick.

9. **Voice check:** zero em dashes, zero contractions, zero banned words. Will re-verify via grep before rendering.

10. **If you want a shorter version** (~150 words for tight forms): drop P2 entirely; keep P1 + P3. Produces on request.

11. **If you want a longer version** (~350 words for rich forms): expand P2 to include Matchbox architectural details + Kubera kill-gate story. Produces on request.

12. **Open questions to confirm before Phase 3 render:**
    - Opener: keep the optometrist story or swap to the production-code-timeline opener?
    - Sign-off: "Happy to talk further" — acceptable?
    - Geo-line content for UK + Relocate variants — as written above, or your own wording?
