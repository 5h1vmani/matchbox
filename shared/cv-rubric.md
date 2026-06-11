# CV quality rubric — the SOTA bar

The deterministic gates (verified bullets only, voice rules, keyword presence)
prove a CV is TRUE and literate. This rubric is the bar for PERSUASIVE. The
tailoring brain self-checks against it while drafting, and every CV that will
actually be submitted must pass a cold read (below) before it is final.

## The eight dimensions

Each scores pass / fail for the specific job being applied to.

1. **Narrative arithmetic.** The summary states the JD's #1 requirement as an
   explicit, pre-computed claim. If the evidence spans eras or employers, the
   summary does the addition; the reader never assembles the case themselves.
2. **Evidence completeness.** The single strongest verified proof for each
   must-have requirement appears on the page. If the library lacks it, that is
   a library gap: draft the missing bullet for the user to verify in Review.
   Never paper over it with wording.
3. **JD-noun mirroring.** The JD's load-bearing nouns appear in bullets or the
   summary, truthfully, in context. Terms buried in the skills list do not
   count as mirroring. Never force a term a bullet cannot honestly carry.
4. **Emphasis order.** The first bullet under each role is the most relevant
   one for THIS job, not the most impressive in general. Infrastructure flexing
   in front of a finance audience is a fail.
5. **Skills signal-to-noise.** Only categories and items this recruiter cares
   about. A 60-item list dilutes; cut to roughly three role-relevant lines.
6. **Band calibration.** The seniority story matches the req's level. Flag
   over- or under-qualification honestly in the run notes instead of papering
   over it.
7. **The 6-second test.** Headline + summary + first two bullets, alone, would
   make this recruiter keep reading.
8. **Timeline continuity.** No unexplained employment gap longer than roughly
   three months. A gap is closed by a compressed entry even when it is
   topically irrelevant to the role, framed by its strongest facet -- a
   sabbatical or volunteer stint becomes a one-line operations or leadership
   entry, not a hole. Dropping a real role to save space is a fail the moment
   it opens a visible gap; cut bullets within the role instead.

## Page discipline

One page tight, or two pages full -- never the accidental 1.2-pager. The
selection's `target_pages` declares the intent (default 1); the core scales
the bullet budget to match and changes.md reports `Pages: N (target M)`.
Choose 2 deliberately: senior or depth-heavy roles where the verified
library holds enough evidence to genuinely fill the second page, and page 1
alone still wins the 6-second test. A thin second page reads as accident,
not seniority -- if a target-2 render lands under roughly 1.5 pages, cut
back to a tight single page instead.

## The cold read

The writer must not grade its own work, so the read happens in a FRESH
context (a subagent, or a separate session) that receives ONLY:

* the JD text,
* the rendered CV text (from cv.json, not the construction artifacts),
* a persona: "You screen candidates for [role] at [company]. You spend six
  seconds deciding whether to keep reading, then at most sixty seconds on a
  full read. Score the seven dimensions of this rubric pass/fail, give a
  shortlist/reject verdict, and name the top three fixes."

No selection rationale, no coverage report, no knowledge of how the CV was
built. The cold reader sees what a recruiter sees: the page.

## Gate and loop bounds

* First pass: ONE cold reader scores the eight dimensions. Ship at >= 7/8
  with no fail on dimensions 1, 2, 7, or 8.
* Below the bar: revise, then compare PAIRWISE -- never re-score in absolute.
  Single-reader absolute scores are too noisy to compare across reads (two
  different judges gave the same pipeline's drafts 7/7 and 4/7 in testing).
  Instead, THREE fresh readers each see both drafts plus the JD, framed as
  "this candidate has two drafts and must submit one" (never as two competing
  candidates -- readers correctly refuse to rank the same person twice), with
  presentation order flipped for at least one reader. Majority wins.
* Maximum two revision loops. Still failing -> surface to the user with the
  votes and the disagreement; never loop silently.
* Cost discipline: cold readers are a small fast model (the scan is pattern
  judgment); revision is the main brain's judgment. Cold-read only CVs that
  will actually be submitted.

## Reality calibration

Rubric scores are proxy. The tracker's response data (response_type per
application) is truth. Periodically compare: which dimensions correlate with
callbacks; tighten or relax the rubric from evidence, not theory.
