# Supported ATS sources

Status as of the v0.3 live-fire pass (2026-05-22). Each row was verified
against a real public job board with no auth header.

| ATS | Status | Endpoint | Verified slug | Jobs seen |
|---|---|---|---|---|
| Greenhouse | ✅ live | `boards-api.greenhouse.io/v1/boards/{slug}/jobs` | `anthropic` | 392 |
| Lever | ✅ live | `api.lever.co/v0/postings/{slug}?mode=json` | `palantir` | 222 |
| Ashby | ✅ live | `api.ashbyhq.com/posting-api/job-board/{slug}` | `linear` | 23 |
| SmartRecruiters | ✅ live | `api.smartrecruiters.com/v1/companies/{slug}/postings` | `Visa` | 20 |
| Recruitee | ✅ live | `{slug}.recruitee.com/api/offers/` | `bunq` | 34 |
| Workable | ⏸ deferred | (vendor removed public no-auth API) | — | — |

## Notes per vendor

### Greenhouse

Slugs are lowercase company names. Anthropic, Stripe, GitLab, Figma all
use Greenhouse boards. A scan against `anthropic` returns hundreds of
jobs; the JD body comes through cleanly after HTML stripping.

### Lever

Slug case matters less but use what the company's job board URL shows.
Many companies have moved off Lever in the last two years; check the
company's careers page before guessing. `palantir` works; companies like
`loom`, `mercury`, `ramp`, `benchling` are not on Lever anymore.

### Ashby

The fastest-growing ATS in the YC-startup tier. Linear, Vercel, and a
lot of newer companies. `linear` returned 23 jobs in the live-fire.

### SmartRecruiters

Slugs are **case-sensitive** and often title-cased (`Visa`, not `visa`).
Enterprise-heavy. Pagination uses `offset`/`limit`; the poller iterates
until it has fetched `totalFound`.

### Recruitee

Subdomain-per-company pattern (`<slug>.recruitee.com`). Popular among
EU-headquartered companies (Dutch, German, Nordic). `bunq` and
`bridgefund` both worked. Some slugs 302 to the live board (`recruitee`
itself redirects to a demo); the poller now follows redirects.

### Workable (deferred)

Workable removed their public no-auth jobs API. The endpoint we
originally targeted (`apply.workable.com/api/v3/accounts/{slug}/jobs`)
now returns 404 for every public slug; the widget endpoint the public
job board uses requires an account-specific token. The
`poll_workable` function in `src/matchbox/discovery/pollers.py` is
preserved (and exercised by mocked tests) so we can re-enable it
when Workable surfaces a no-auth endpoint or when we add a per-source
`auth_token` field on `ats_source`. Until then it is intentionally
absent from the `POLLERS` dispatch and from the `/sources` add-form.

## Adding more

If you find another ATS with a stable public JSON API, add a poller in
`src/matchbox/discovery/pollers.py` following the same pattern (one
function returning `list[JobRecord]`, registered in `POLLERS`), and add
a row here documenting the verified slug. The schema's `ats_type`
CHECK constraint already includes Teamtailor, Personio, Breezy HR, and
JazzHR — the design called them out as stretch candidates. Pick one,
verify against a real public slug, ship the poller.
