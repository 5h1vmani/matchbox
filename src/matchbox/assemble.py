"""assemble — deterministic selection and rendering for a job.

Placeholder in M0. Real implementation lands in M5. Invoked by the brain:

    python -m matchbox.assemble --run <run_id> --job <job_id>
    python -m matchbox.assemble --run <run_id> --job <job_id> --cover
"""

from __future__ import annotations

import sys


def main(argv: list[str] | None = None) -> int:
    print("matchbox.assemble: not yet implemented (lands in M5)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
