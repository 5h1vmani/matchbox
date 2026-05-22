# Demo Stories

<!-- STAR+R format. This is a demo profile — content is illustrative only. -->

## Cut deploy time from 30 minutes to 90 seconds

**Situation:** Engineering team of 12 was deploying twice a day, each deploy taking 30 minutes of CI plus manual smoke tests.

**Task:** Halve the deploy time without sacrificing reliability.

**Action:** Profiled the CI pipeline, parallelised the test suite, switched to incremental Docker builds, replaced the smoke-test runbook with a synthetic-traffic check.

**Result:** Median deploy time fell to 90 seconds. Deploy frequency rose 8x in the following quarter.

**Reflection:** The biggest unlock was treating "manual smoke test" as the bottleneck rather than CI compute. Talking to the on-call engineers surfaced what we were actually checking for; once we automated that, the rest was cleanup.
