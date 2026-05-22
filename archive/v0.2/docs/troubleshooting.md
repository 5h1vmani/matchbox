# Troubleshooting

Symptoms → causes → fixes. Search this page (`Ctrl+F` / `⌘F`) before opening an issue.

## Install / setup

### `pip install -e ".[dev]"` fails with `externally-managed-environment`

You're on a system Python that PEP 668 protects. Two clean fixes:

```bash
# Option 1 (recommended): use uv to manage the venv
uv sync --dev

# Option 2: use a virtualenv
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

The `--break-system-packages` flag works but contaminates the system Python — avoid it.

### `matchbox: command not found` after install

The `matchbox` script lives in your Python's `bin/` dir. Either:

* Activate the venv: `source .venv/bin/activate`.
* Or run it as a module: `python -m matchbox.cli --help`.

### `typst: command not found` when running `matchbox tailor`

Typst is a system binary, not a Python package. Install it:

```bash
brew install typst                # macOS
cargo install typst-cli           # any platform
# Or download a release: https://github.com/typst/typst/releases
typst --version                   # verify
```

Tailor only needs Typst for the actual PDF render. Scan / score / web all work without it.

### `ANTHROPIC_API_KEY not set`

Set it in your shell or in `.env` (gitignored):

```bash
export ANTHROPIC_API_KEY=sk-ant-...
# Or:
echo "ANTHROPIC_API_KEY=sk-ant-..." >> .env
```

Only `matchbox tailor` needs this. Scan / score / web all work without it.

## Web dashboard

### "No profiles found" on the welcome page

You haven't created a profile yet. Two options:

```bash
matchbox seed-demo            # 30 synthetic jobs in people/demo/
# OR
matchbox init-profile alice   # then edit people/alice/profile.yaml
```

### Inbox is empty after `matchbox scan`

Check the actual scan output. The CLI prints `inserted=N`. If `N == 0`, nothing matched after exclusions. Common causes:

* Your `targets.primary_roles` doesn't overlap with what was scanned. Open `profile.yaml` and broaden it.
* Your `filters.exclusions` blocks the country / sector. Check `docs/architecture.md` for the exclusion logic.
* The ATS source is dry that day — run `matchbox scan alice --verbose` to see per-source counts.

### Bulk tailor cap "5 jobs"

Intentional. Each LLM call is 5–30 seconds; UI requests would time out for larger batches. Use the CLI:

```bash
matchbox tailor alice 12 14 17 21 28 33 47   # 7 jobs in sequence
```

Or tailor them one at a time from the inbox.

### "Cost confirmation required" on bulk tailor

The cumulative high-end estimate is above `MATCHBOX_COST_CONFIRM_USD` (default $1). The preview modal has a "Confirm and tailor" button. If you want a different threshold:

```bash
export MATCHBOX_COST_CONFIRM_USD=5.0
matchbox web
```

### Web dashboard binds to wrong host

Defaults to `127.0.0.1:8765`. Override with:

```bash
matchbox web --host 0.0.0.0 --port 9000     # PRINTS A RED WARNING — read it
```

The warning is intentional. **Do not** expose to the network without a reverse proxy + auth (see [SECURITY.md](../SECURITY.md)).

### Toasts don't appear

Check the browser console. Likely causes:

* Browser is blocking JS (disable shields/extensions for `127.0.0.1`).
* Custom Content Security Policy in your browser is blocking the inline `<script>` tags. Tailwind Play CDN + Alpine + HTMX all need to load.

## Profile editor

### "profile.yaml is malformed" toast

Your YAML has a syntax error. The error includes the offending line. Fix it in your editor and reload — the message tells you what ruamel saw.

### Save succeeds but scores didn't change

By design. Saving weights only affects **future** scans. To re-score existing jobs:

```bash
matchbox score-job alice 42       # one job at a time
# Bulk re-score from the CLI is on the roadmap.
```

The Profile page's "Live preview" shows what the *new* scores would be without writing anything.

## Tailor / LLM

### Tailor returns an empty PDF

Check `matchbox tailor alice 42 --verbose`. Most often:

* Quality gates rejected everything (`--gate-mode warn` continues; `raise` aborts).
* The Anthropic response failed to validate against the tool-use schema. Re-run.

### Cost was higher than the estimate

The estimate range is heuristic — bespoke is typed as $10–20. If the JD is unusually long or the model regenerated heavily, you can land outside that range. The `analytics` page tracks actual spend per tier so you can recalibrate.

### "Gate violation" warnings in the panel

Expected when `gate_mode=warn` (the default). The PDF is still rendered; the operator decides whether to accept it. To get a clean tailor, edit `voice.yaml` or `stories.md` and re-tailor.

## Tests / development

### `pytest` fails with `IntegrityError: UNIQUE constraint failed`

A test left state in `people/demo/db.sqlite`. Clean it:

```bash
rm people/demo/db.sqlite
pytest -q                         # fixture re-seeds
```

### Pre-commit hook fails on a clean checkout

```bash
pre-commit clean
pre-commit install --install-hooks
pre-commit run --all-files
```

If a specific hook is failing for a reason you understand, fix the underlying issue — don't bypass with `--no-verify`. That's [muscle-memory poison](../docs/decisions/0007-no-strictness-hooks-yet.md) we deliberately avoid.

### CI fails but pre-commit passes locally

Pre-commit and CI are designed to run the same checks. If they diverge, it's a bug — file an issue. Common reasons:

* Pre-commit hook version is stale: `pre-commit autoupdate`.
* A file isn't tracked by git, so pre-commit didn't see it.
* Your local Python is a different minor version than CI's 3.12.

## Anything else

Open a [discussion](https://github.com/5h1vmani/matchbox/discussions) or a [bug report](https://github.com/5h1vmani/matchbox/issues/new/choose) (with the template — please don't skip the fields, they're there for a reason).
