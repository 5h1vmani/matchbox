#!/usr/bin/env bash
# One-command setup: python deps, SPA build, then a doctor pass.
set -euo pipefail

cd "$(dirname "$0")/.."

if command -v uv >/dev/null 2>&1; then
    echo "==> installing python deps (uv sync --extra dev)"
    uv sync --extra dev
    RUNNER=(uv run matchbox-doctor)
else
    echo "==> uv not found; falling back to pip (python3 -m pip install -e '.[dev]')"
    python3 -m pip install -e ".[dev]"
    RUNNER=(python3 -m matchbox.doctor)
fi

# The SPA is optional for the CLI workflow, so a missing npm must not undo
# the python install we just finished.
if command -v npm >/dev/null 2>&1; then
    echo "==> building the SPA (frontend/)"
    (cd frontend && npm install && npm run build)
else
    echo "==> npm not found; skipping the SPA build (install node from https://nodejs.org, then: cd frontend && npm install && npm run build)"
fi

echo "==> running the doctor"
"${RUNNER[@]}"

echo "next: matchbox-web -> http://127.0.0.1:8765"
