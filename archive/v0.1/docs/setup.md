# Setup Guide

First-time setup for a new machine, new profile, or after a long break.

## Prerequisites

- macOS (the team runs on macOS; Linux should work with path adjustments)
- Python 3.12+ (`python3 --version`)
- `claude` CLI installed and authenticated (for running slash commands)
- Chrome or Chromium installed at `/Applications/Google Chrome.app/` (required for PDF generation)
- curl (macOS default)

## 1. Install Python dependencies

```bash
pip install --break-system-packages --user streamlit pyyaml
```

The `--break-system-packages --user` flag is needed on macOS with system Python. Installs into `~/Library/Python/3.12/`.

## 2. Add Streamlit to your PATH (optional but convenient)

```bash
echo 'export PATH="$HOME/Library/Python/3.12/bin:$PATH"' >> ~/.zshrc
source ~/.zshrc
```

After this, `streamlit --version` should work directly.

Or, always use `python3 -m streamlit` instead of `streamlit`.

## 3. Disable Streamlit telemetry

Already done — `.streamlit/config.toml` at the repo root disables the email prompt. Verify:

```bash
cat /Users/yantram/Desktop/Pinaka_speckit/.streamlit/config.toml
```

Should show `gatherUsageStats = false`.

## 4. Download the fonts (one-time, for CV rendering)

Already done for Shiva's profile. For a new machine:

```bash
cd /Users/yantram/Desktop/Pinaka_speckit/atma/shared/fonts

curl -sL -o AtkinsonHyperlegible-Regular.ttf https://raw.githubusercontent.com/googlefonts/atkinson-hyperlegible/main/fonts/ttf/AtkinsonHyperlegible-Regular.ttf
curl -sL -o AtkinsonHyperlegible-Bold.ttf https://raw.githubusercontent.com/googlefonts/atkinson-hyperlegible/main/fonts/ttf/AtkinsonHyperlegible-Bold.ttf
curl -sL -o AtkinsonHyperlegible-Italic.ttf https://raw.githubusercontent.com/googlefonts/atkinson-hyperlegible/main/fonts/ttf/AtkinsonHyperlegible-Italic.ttf

curl -sL -o IBMPlexSans-Variable.ttf "https://raw.githubusercontent.com/google/fonts/main/ofl/ibmplexsans/IBMPlexSans%5Bwdth%2Cwght%5D.ttf"
curl -sL -o IBMPlexSans-Italic-Variable.ttf "https://raw.githubusercontent.com/google/fonts/main/ofl/ibmplexsans/IBMPlexSans-Italic%5Bwdth%2Cwght%5D.ttf"

curl -sL -o Manrope-Regular.ttf https://raw.githubusercontent.com/google/fonts/main/ofl/manrope/Manrope%5Bwght%5D.ttf

ls -la *.ttf
```

All five files should be 50KB-600KB. If any is 0 bytes or plain text, the URL is broken; check GitHub for the current path.

## 5. Initialise the SQLite DB

The DB is created on first use, no manual step required. To verify manually:

```bash
cd /Users/yantram/Desktop/Pinaka_speckit
python3 matchbox/shared/db.py shiva
```

Should print:
```
Schema initialised at: /Users/yantram/Desktop/Pinaka_speckit/matchbox/people/shiva/db/matchbox.db
...
Smoke test passed.
```

Then delete the test data:
```bash
rm -rf matchbox/people/_smoke_test
```

## 6. Verify Atma identity layer is populated

Your profile should have:
```
atma/people/shiva/
├── index.md
├── routing.md
├── sensitivity.md
└── wiki/
    ├── profile.yml       your targets, comp, dream companies
    ├── cv.md             master CV
    ├── narrative.md      positioning
    ├── voice.md          style rules
    ├── skills.md
    ├── projects.md
    ├── story-bank.md
    ├── preferences.md
    └── log.md
```

If any are missing, see `atma/people/shiva/index.md` for the canonical structure.

## 7. First scan — small trial

In Claude Code (chat), run:

```
/marathon --profile shiva --trial --modes dream --countries india
```

Should complete in ~8 minutes, cost ~$3, produce ~15-30 scored jobs.

Verify the DB has rows:
```bash
cd /Users/yantram/Desktop/Pinaka_speckit
python3 -c "
import sys; sys.path.insert(0, '.')
from matchbox.shared import db
print(db.get_stats('shiva'))
"
```

Should show `count_evaluated` > 0.

## 8. Launch the UI

```bash
cd /Users/yantram/Desktop/Pinaka_speckit
python3 -m streamlit run matchbox/ui/ui.py --server.port 8501
```

Open http://localhost:8501. You should see the scored jobs from the trial.

## 9. You are set up

Go read [operator-runbook.md](operator-runbook.md).

## Common setup issues

### `streamlit: command not found`

Either use `python3 -m streamlit run ...`, or add the user pip bin to your PATH (step 2).

### `ModuleNotFoundError: matchbox.shared`

You ran a Python command from the wrong directory. Always `cd /Users/yantram/Desktop/Pinaka_speckit` first.

### `sqlite3.OperationalError: database is locked`

Something else is writing to the DB. Close the UI, wait a few seconds, retry. If persistent:
```bash
rm matchbox/people/shiva/db/matchbox.db-wal matchbox/people/shiva/db/matchbox.db-shm
```

### Chrome not found for PDF generation

If you installed Chrome in a non-standard location, update the `CHROME` path in any script that uses it. Grep for `/Applications/Google Chrome.app` to find usages.

### `.streamlit/config.toml` not being read

Ensure it is at the repo root (same level as the `matchbox/` folder), not inside `matchbox/`. Streamlit looks for it at the current working directory.
