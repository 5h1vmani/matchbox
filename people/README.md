# people/

Each subdirectory is one candidate profile. All profile directories are
gitignored except `demo/` (which exists so the v0.3 demo flow has a place
to land its `matchbox.db`).

The active profile is chosen by the `MATCHBOX_PROFILE` env var (defaults
to `demo`). The path is resolved as `people/<MATCHBOX_PROFILE>/matchbox.db`.
`MATCHBOX_DB` overrides the whole path when set.

Per-profile layout (v0.3):

```text
people/<slug>/
  matchbox.db        Single SQLite DB. Profile row, library, jobs, runs,
                     applications, embeddings, settings. Gitignored.
```

Earlier versions kept YAML (`profile.yaml`, `voice.yaml`, `stories.md`,
`anchor-packs.yaml`) per profile. v0.3 dropped all of that. Profile data
is rows in the DB now; voice rules and the scoring rubric live in
`shared/` and are repo-wide.

To create a new profile:

```bash
MATCHBOX_PROFILE=alice matchbox-web
```

The DB is created on first request. Use the web UI to populate it.
