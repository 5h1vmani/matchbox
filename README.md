# Matchbox v0.2

Precision job application pipeline. Scan ATS boards → score by fit → tailor at the right cost tier → track outcomes.

## What it does

| Step | Command | Cost |
|------|---------|------|
| Scan KNOWN_SOURCES (20+ ATS boards) | `matchbox scan shiva` | $0 |
| Score on 6 dimensions (heuristic) | automatic | $0 |
| Route: bespoke / template / canonical / skip | automatic | $0 |
| Generate tailored CV + cover | `matchbox tailor shiva 42` | $0.05–$20 |
| Track outcomes | `matchbox log-response shiva 42 interview` | $0 |
| Analytics + funnel | `matchbox analytics shiva` | $0 |

## Quick start

```bash
# Install (requires Python 3.12+, uv recommended)
pip install -e ".[dev]"

# Try the dashboard with synthetic demo data (no API key needed)
matchbox seed-demo
matchbox web                 # opens at http://127.0.0.1:8765

# Or use a real profile
matchbox init-profile alice
matchbox scan alice --dry-run

# Full help
matchbox --help
```

See [docs/setup.md](docs/setup.md) for full setup including Typst and API keys.

## Repository layout

```
matchbox/
├── src/matchbox/
│   ├── core/          # Schema, DB, person loader, exceptions
│   ├── scoring/       # Exclusions, rubric, tier router
│   ├── discovery/     # ATS probers, daily scan, funding scan
│   ├── tailor/        # Gates, content gen, Typst render, dispatch
│   ├── outcome/       # Response logging, follow-ups, analytics
│   ├── ui/            # Streamlit dashboard
│   └── cli.py         # Typer entry point
├── people/
│   └── shiva/
│       ├── profile.yaml        # Structured profile (SSOT)
│       ├── voice.yaml          # LLM voice rules
│       ├── stories.md          # STAR+R narratives
│       ├── anchor-packs.yaml   # Pre-approved bullets by role family
│       ├── log.md              # Application log
│       └── output/             # Generated PDFs (gitignored)
├── shared/
│   ├── rubric.yaml             # 6-dimension scoring weights
│   ├── voice-rules.yaml        # Universal voice constraints
│   └── templates/              # Typst CV + cover templates
├── tests/
└── docs/
```

## Tier routing

| Score (0–5) | Normalised | Tier | Estimated cost |
|-------------|-----------|------|----------------|
| ≥ 4.0 | ≥ 0.80 | bespoke | $10–20 (full Sonnet rewrite) |
| ≥ 3.0 | ≥ 0.60 | template | $0.05–0.30 (anchor pack + Sonnet) |
| ≥ 2.0 | ≥ 0.40 | canonical | $0 (pre-rendered PDF copy) |
| < 2.0 | < 0.40 | skip | $0 |

## Profiles

Each person has their own directory under `people/`. To add a new profile:

```bash
matchbox init-profile alice
# Edit people/alice/profile.yaml
matchbox scan alice --dry-run
```

## Security note

Matchbox is a single-user local tool with **no auth, no CSRF protection, and
no rate limiting.** The dashboard binds to `127.0.0.1` by default. Do not
expose it to the network. If you need remote access, put it behind a reverse
proxy with auth — anyone who can reach the port can read your jobs and spend
your Anthropic API budget.

## License

MIT
