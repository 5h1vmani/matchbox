#!/usr/bin/env bash
# Block any commit under people/ except people/demo/ and people/README.md.
#
# Defense-in-depth: .gitignore already excludes people/*, but a rule
# can drift. This hook makes the failure mode loud and explicit.

set -e

violations=0
for file in "$@"; do
    if [[ "$file" =~ ^people/([^/]+)(/|$) ]]; then
        name="${BASH_REMATCH[1]}"
        # Allow: people/README.md and people/demo/**
        if [[ "$name" == "README.md" || "$name" == "demo" ]]; then
            continue
        fi
        echo "Refusing to commit: $file"
        violations=$((violations + 1))
    fi
done

if [[ $violations -gt 0 ]]; then
    echo ""
    echo "Real profiles must stay local. Only people/demo/ may be committed."
    echo "Run: git rm --cached <file> to untrack."
    exit 1
fi
