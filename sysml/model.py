"""Assemble and evaluate the GeoSatADCS SysML v2 model with OpenSysML 0.10.0.

Three blocks, three owners, spliced into one package:
  structure    hand-authored, static, in Git         (sysml/satellite.sysml)
  evidence     generated from scipy results          (evidence_block)
  attestation  written only by a human action        (attestation_block)

Verdicts and `holds` are verification (automated). The attestation is the human's
`satisfy` plus its StatusInfo; `evaluate` only checks the claim for consistency.
"""

from __future__ import annotations

import re
from pathlib import Path

import opensysml

VERSION = "v0.10.0"
PACKAGE = "GeoSatADCS"
STRUCTURE_PATH = Path(__file__).with_name("satellite.sysml")

# Names that must never be recorded as the human who attested. A blunt guard, not a
# security boundary: copied from sysmlv2-testing (same trust model as git authorship).
NOT_A_HUMAN = frozenset({"svt", "svt-cli", "cli", "claude", "llm", "ai", "agent", "bot", "assistant"})

# The demo uses only two statuses: "tbc" (pending, the human has not yet decided) and
# "done" (attested). The rest of StatusKind (for example inwork, closed) is not used, so
# anything else is refused rather than silently recorded.
_STATUS = {"tbc", "done"}
_IDENT = re.compile(r"^[A-Za-z_]\w*$")

# The human's draft adequacy judgement, for the notebook to pre-fill. It is not a finding.
DEFAULT_ADEQUACY = (
    "The simulation clips control torque at the actuator limit, so peak torque cannot exceed "
    "the limit in this model; whether operating at saturation is acceptable is not answered "
    "by this model."
)


def _q(text: str) -> str:
    """Escape text for a SysML string literal."""
    return text.replace("\\", "\\\\").replace('"', '\\"').replace("\n", " ")


def _ident(kind: str, value: str) -> str:
    if not isinstance(value, str) or not _IDENT.fullmatch(value):
        raise ValueError(f"{kind} {value!r} is not a SysML identifier (^[A-Za-z_]\\w*$)")
    return value


def evidence_block(design: str, params: dict, summary: dict, sim_hash: str, adequacy: str) -> str:
    """The generated block for one design. `params` has Kp, Kd, maxTorque;
    `summary` is SimResult.summary(); `sim_hash` comes from evidence.hashing.hash_simulation.

    `adequacy` is the Rationale text: a person's judgement (validation) that the model is
    adequate for this use, carried with the evidence. The caller supplies it; this function
    makes no judgement of its own."""
    _ident("design", design)
    return f"""\
    // ----- Rationale below is a person's adequacy judgement, carried with the evidence -----
    part {design} : ADCS {{
        attribute :>> Kp = {float(params['Kp'])!r};
        attribute :>> Kd = {float(params['Kd'])!r};
        attribute :>> settlingTime = {float(summary['settling_time_s'])!r} [s];
        attribute :>> peakTorque = {float(summary['peak_control_torque'])!r} [N*m];
        attribute :>> torqueLimit = {float(params['maxTorque'])!r} [N*m];
    }}
    metadata : AnalysisTooling::ToolExecution about {design} {{
        toolName = "scipy solve_ivp (analysis/numerical.py)";
        uri = "sha256:{sim_hash}";
    }}
    metadata : ModelingMetadata::Rationale about {design} {{
        text = "{_q(adequacy)}";
    }}
    verification vc001_{design} : SettlingVerification {{ subject = {design}; }}
    verification vc004_{design} : DisturbanceVerification {{ subject = {design}; }}
"""


def attestation_block(design: str, satisfied: bool, originator: str, status: str,
                      sufficiency: str, verification: str) -> str:
    """The human's claim (usage-subsetting form, which OpenSysML 0.10.0 evaluates and which traces to req001) with StatusInfo and the sufficiency Rationale.
    Refuses an empty originator or one in NOT_A_HUMAN."""
    _ident("design", design)
    _ident("verification", verification)
    who = originator.strip()
    if not who or who.lower() in NOT_A_HUMAN:
        raise ValueError(f"originator {originator!r} is not a named human")
    if status not in _STATUS:
        raise ValueError(f"status must be one of {sorted(_STATUS)}, got {status!r}")
    neg = "" if satisfied else "not "
    return f"""\
    {neg}satisfy requirement att_{design} :> req001 by {design};
    metadata : ModelingMetadata::StatusInfo about att_{design} {{
        originator = "{_q(who)}";
        status = StatusKind::{status};
    }}
    metadata : ModelingMetadata::Rationale about att_{design} {{
        text = "{_q(sufficiency)}";
        explanation = {verification};
    }}
"""


def _banner(label: str, owner: str) -> str:
    return f"    // ===== {label} block ({owner}) =====\n"


def assemble(structure: str, evidence: str = "", attestation: str = "") -> str:
    """Splice the evidence and attestation blocks before the package's closing brace."""
    head, brace, tail = structure.rstrip().rpartition("}")
    if not brace:
        raise ValueError("structure has no closing brace")
    parts = [head.rstrip() + "\n\n"]
    if evidence:
        parts.append(_banner("evidence", "generated by Python from scipy") + evidence + "\n")
    if attestation:
        parts.append(_banner("attestation", "written only by a human") + attestation)
    parts.append("}\n")
    return "".join(parts)


def load_structure() -> str:
    return STRUCTURE_PATH.read_text()


def evaluate(text: str) -> dict:
    """Load `text` with OpenSysML (strict) and return plain Python:
    diagnostics, verdicts (verification usage -> kind), claims (att_* -> holds/error),
    req ("req001(design)" -> bool)."""
    conn = opensysml.connect(version=VERSION)
    try:
        model = conn.load_from_content(text, strict=True)
        diagnostics = [f"{d.severity}: {d.message}" for d in model.diagnostics]
        verdicts = {
            name: model.run_analysis(f"{PACKAGE}::{name}").verifications[0].kind
            for name in re.findall(r"^\s*verification\s+(vc\d+_\w+)\s*:", text, re.M)
        }
        claims = {}
        for name in re.findall(r"satisfy\s+requirement\s+(att_\w+)\s*:>", text):
            v = model.verify_satisfaction(f"{PACKAGE}::{name}")[0]
            claims[name] = {"holds": bool(v.holds) if not v.error else None, "error": v.error or None}
        req = {}
        for design in re.findall(r"^\s*part\s+(\w+)\s*:\s*ADCS\b", text, re.M):
            for r in ("req001", "req004"):
                req[f"{r}({design})"] = bool(model.eval(f"{PACKAGE}::{r}({PACKAGE}::{design})"))
        return {"diagnostics": diagnostics, "verdicts": verdicts, "claims": claims, "req": req}
    finally:
        conn.close()
