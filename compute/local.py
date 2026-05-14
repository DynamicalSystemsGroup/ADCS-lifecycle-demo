"""LocalCompute — in-process analysis (the original fast path).

Captures hostname and Python version into ExecutionMetadata so even
local runs carry a "where was this computed" record into RTM
provenance. That keeps the audit trail uniform regardless of compute
backend: an engineer's machine is just a particular kind of execution
location, recorded explicitly rather than implicitly.
"""

from __future__ import annotations

import platform
import socket
from datetime import datetime, timezone
from typing import Any

from analysis.numerical import run_disturbance_rejection as _run_dist
from analysis.numerical import run_step_response as _run_step
from analysis.symbolic import run_symbolic_analysis as _run_sym
from compute.base import ExecutionMetadata


class LocalCompute:
    name = "local"

    def describe(self) -> str:
        return (
            f"Local in-process compute "
            f"(host={socket.gethostname()}, python={platform.python_version()})"
        )

    def _run(self, fn, params, stage_label: str):
        started = datetime.now(timezone.utc).isoformat()
        result = fn(params)
        ended = datetime.now(timezone.utc).isoformat()
        metadata = ExecutionMetadata(
            location_kind="local",
            hostname=socket.gethostname(),
            python_version=platform.python_version(),
            started_at=started,
            ended_at=ended,
        )
        return result, metadata

    def run_symbolic_analysis(self, params: dict) -> tuple[Any, ExecutionMetadata]:
        return self._run(_run_sym, params, "symbolic")

    def run_step_response(self, params: dict) -> tuple[Any, ExecutionMetadata]:
        return self._run(_run_step, params, "step")

    def run_disturbance_rejection(self, params: dict) -> tuple[Any, ExecutionMetadata]:
        return self._run(_run_dist, params, "disturbance")
