#!/usr/bin/env bash
# Block real-PII patterns in staged files.
#
# Targets:
#   - Phone numbers in real country-code formats (+91, +44, +1, +33, +49)
#   - Emails at common consumer providers (gmail, yahoo, outlook, etc.)
#
# Will NOT match: test@example.com, +00 0000000000, etc.
# Allowlist: people/demo/, tests/, docs/, README.md, CONTRIBUTING.md
#
# Failure means: move the value to people/{name}/ (gitignored), or
# replace with a placeholder like test@example.com.

set -e

PHONE_RE='\+(91|44|1|33|49)[ -]?[0-9]{10}'
EMAIL_RE='[A-Za-z0-9._%+-]+@(gmail|yahoo|outlook|hotmail|icloud|protonmail|aol|live|msn)\.(com|in|co\.uk|co\.in|net|org)'
ALLOWLIST='^(people/|tests/|docs/|README\.md|CONTRIBUTING\.md|\.githooks/|\.pre-commit-config\.yaml|\.gitleaks\.toml|plans/)'

violations=0
for file in "$@"; do
    if [[ "$file" =~ $ALLOWLIST ]]; then
        continue
    fi
    if [[ ! -f "$file" ]]; then
        continue
    fi
    if matches=$(grep -E -H -n -e "$PHONE_RE" -e "$EMAIL_RE" "$file" 2>/dev/null); then
        echo "$matches"
        violations=$((violations + 1))
    fi
done

if [[ $violations -gt 0 ]]; then
    echo ""
    echo "PII patterns detected. Options:"
    echo "  1. Move to people/{name}/ (gitignored)"
    echo "  2. Replace with placeholder (test@example.com / +00 0000000000)"
    echo "  3. Add path to ALLOWLIST in .githooks/pii-scan.sh if intentional"
    exit 1
fi
