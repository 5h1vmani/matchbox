#!/usr/bin/env bash
# Pre-push gate: the last local stop before code leaves the machine.
#
# Catches secrets or PII that slipped past pre-commit -- a `--no-verify`
# commit, or commits authored on a machine without the hooks installed.
# It mirrors the CI `security` job, and both reuse the same two scripts
# (people-guard.sh, pii-scan.sh) so the rules never drift across layers.
#
# Unlike the commit-stage gitleaks hook (which scans the *staged* diff),
# this runs `gitleaks detect` over full history -- the right scan for push.
#
# Activate:  pre-commit install --hook-type pre-push
set -euo pipefail

root="$(git rev-parse --show-toplevel)"
cd "$root"

fail=0

# 1. Secrets across full history.
if command -v gitleaks >/dev/null 2>&1; then
    if ! gitleaks detect --no-banner --redact; then
        echo "pre-push: gitleaks found secrets in history. Push blocked." >&2
        fail=1
    fi
else
    echo "pre-push: gitleaks not installed; skipping the secret scan." >&2
    echo "          Install it (brew install gitleaks) -- CI still enforces this." >&2
fi

# 2. PII patterns + the people/ guard, over every tracked file.
if ! git ls-files -z | xargs -0 .githooks/people-guard.sh; then fail=1; fi
if ! git ls-files -z | xargs -0 .githooks/pii-scan.sh; then fail=1; fi

if [[ $fail -ne 0 ]]; then
    echo "" >&2
    echo "Push blocked by the pre-push gate. Fix the findings above before pushing." >&2
    exit 1
fi
