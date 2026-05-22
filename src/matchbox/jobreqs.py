"""jobreqs — save the brain's extracted JD requirements.

Placeholder in M0. Real implementation lands in M5 alongside the matching
module. Invoked by the brain:

    python -m matchbox.jobreqs save --job <id> --file <reqs.json>
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    print("matchbox.jobreqs: not yet implemented (lands in M5)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
