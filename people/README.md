# people/

Each subdirectory is one candidate profile. All profile directories are gitignored except `demo/`.

To create your profile:

```bash
matchbox init-profile --name yourname
```

Or copy `demo/` as a starting point:

```bash
cp -r people/demo people/yourname
# then edit people/yourname/profile.yaml
```

Each profile directory contains:
- `profile.yaml` — structured identity, targets, work history, skills, projects
- `voice.yaml` — per-person voice rules and example phrasings (merges with shared/voice-rules.yaml)
- `stories.md` — STAR+R narratives for cover letters and interview prep
- `anchor-packs.yaml` — pre-approved bullet variants per role family (generated from profile.yaml)
- `db.sqlite` — pipeline state (gitignored)
- `output/` — tailored CVs and cover letters per job (gitignored)
- `runs/` — scan run artefacts (gitignored)
- `reports/` — per-role evaluation reports (gitignored)
- `log.md` — activity log (written via `matchbox log-response` only)
