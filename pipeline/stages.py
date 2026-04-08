"""Lifecycle stage enum and gate checks."""

from __future__ import annotations

from enum import IntEnum


class LifecycleStage(IntEnum):
    STRUCTURAL_DEFINED = 1
    SYMBOLICALLY_ANALYZED = 2
    NUMERICALLY_SIMULATED = 3
    EVIDENCE_BOUND = 4
    RTM_ASSEMBLED = 5
    ATTESTATION = 6
    REPORTED = 7
    VISUALIZED_AND_INTERROGABLE = 8


def check_gate(current: LifecycleStage, required: LifecycleStage) -> None:
    """Raise if we haven't reached the required stage yet."""
    if current < required:
        raise RuntimeError(
            f"Stage gate violation: at {current.name}, "
            f"need {required.name} (stage {required.value})"
        )
