"""Container entrypoint — runs inside the adcs-compute image.

The host invokes this with the stage name and a JSON params file:

    uv run python -m compute.container_entry \
        --stage symbolic --params /io/params.json --output /io/results.json

The script:
  1. Captures its own execution context (hostname seen inside the
     container, Python version) — these are the values that get into
     the host-side ExecutionMetadata.
  2. Runs the requested analysis. The full result object isn't
     marshalled back to the host (SymPy / scipy objects don't pickle
     across processes cleanly); the host re-computes locally and uses
     the container's metadata for provenance. This is intentional for
     the demo — production would emit structured JSON results here.
  3. Writes the captured metadata to <output>.
"""

from __future__ import annotations

import argparse
import json
import platform
import socket
import sys
from datetime import datetime, timezone
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description="ADCS analysis container entrypoint")
    parser.add_argument("--stage", choices=["symbolic", "step", "disturbance"],
                        required=False, default=None,
                        help="Which analysis stage to execute")
    parser.add_argument("--params", type=Path, required=False,
                        help="Path to JSON file with analysis parameters")
    parser.add_argument("--output", type=Path, required=False,
                        help="Path to write metadata JSON")
    parser.add_argument("--describe", action="store_true",
                        help="Print container info and exit (default CMD)")
    args = parser.parse_args()

    started = datetime.now(timezone.utc).isoformat()
    info = {
        "hostname": socket.gethostname(),
        "python_version": platform.python_version(),
        "platform": platform.platform(),
        "started_at": started,
    }

    if args.describe or not args.stage:
        json.dump(info, sys.stdout, indent=2)
        sys.stdout.write("\n")
        return 0

    # Validate params file
    if not args.params or not args.params.exists():
        print(f"ERROR: --params not provided or missing: {args.params}",
              file=sys.stderr)
        return 2
    params = json.loads(args.params.read_text())

    # Lazy import so --describe stays cheap.
    if args.stage == "symbolic":
        from analysis.symbolic import run_symbolic_analysis as fn
    elif args.stage == "step":
        from analysis.numerical import run_step_response as fn
    elif args.stage == "disturbance":
        from analysis.numerical import run_disturbance_rejection as fn
    else:
        print(f"ERROR: unknown stage {args.stage!r}", file=sys.stderr)
        return 3

    # Run the stage. Result objects aren't serialized — the host
    # re-computes locally for the analysis result and uses our
    # metadata for provenance.
    try:
        _ = fn(params)
    except Exception as exc:
        info["error"] = str(exc)
        info["ended_at"] = datetime.now(timezone.utc).isoformat()
        if args.output:
            args.output.write_text(json.dumps(info, default=str))
        print(f"ERROR running {args.stage}: {exc}", file=sys.stderr)
        return 4

    info["stage"] = args.stage
    info["ended_at"] = datetime.now(timezone.utc).isoformat()

    if args.output:
        args.output.write_text(json.dumps(info, default=str))
    else:
        json.dump(info, sys.stdout, indent=2)
        sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
