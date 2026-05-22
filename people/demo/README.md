# people/demo/

Placeholder directory for the demo profile.

`matchbox.db` is created here the first time you start the web server
with `MATCHBOX_PROFILE=demo` (the default). Both `matchbox.db` itself
and any `matchbox.db-wal` / `matchbox.db-shm` companions are gitignored.

For the v0.3 quickstart, see the top-level [README.md](../../README.md).

Earlier versions of this directory carried YAML profile files. Those
moved to `archive/v0.2/people-demo/` when the v0.3 schema replaced them
with rows in the SQLite DB.
