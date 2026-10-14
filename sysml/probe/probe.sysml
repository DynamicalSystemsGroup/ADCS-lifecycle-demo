// Probe model: requirement -> evidence -> automated verdict -> human attestation.
// Placeholders (__BAD_ST__, __GOOD_ST__, __BAD_PT__, __GOOD_PT__, __LIMIT__) are
// substituted by run_probe.py with values computed by the scipy step response.
package ProbePkg {
    private import ScalarValues::*;
    private import ISQ::*;
    private import SI::*;
    private import VerificationCases::*;
    private import ModelingMetadata::*;
    private import AnalysisTooling::*;

    part def ADCS {
        attribute settlingTime : ISQ::DurationValue;
        attribute peakTorque : ISQ::TorqueValue;
        attribute torqueLimit : ISQ::TorqueValue;
    }

    // REQ-001 style: settling time within 120 s
    requirement def SettlingReq {
        doc /* The ADCS shall settle within 120 seconds of a slew maneuver. */
        subject adcs : ADCS;
        require constraint { adcs.settlingTime <= 120 [s] }
    }
    requirement req001 : SettlingReq;

    // REQ-004 style: peak torque within actuator capacity
    requirement def TorqueReq {
        doc /* Control torque shall not exceed actuator torque capacity. */
        subject adcs : ADCS;
        require constraint { adcs.peakTorque <= adcs.torqueLimit }
    }
    requirement req004 : TorqueReq;

    // Candidate designs; values come from the scipy run
    part weak : ADCS {
        attribute :>> settlingTime = __BAD_ST__ [s];
        attribute :>> peakTorque = __BAD_PT__ [N * m];
        attribute :>> torqueLimit = __LIMIT__ [N * m];
    }
    part tuned : ADCS {
        attribute :>> settlingTime = __GOOD_ST__ [s];
        attribute :>> peakTorque = __GOOD_PT__ [N * m];
        attribute :>> torqueLimit = __LIMIT__ [N * m];
    }

    // Verification: explicit inequality form
    verification def SettlingCheckExplicit {
        subject adcs : ADCS;
        objective { verify req001; }
        return verdict : VerdictKind = PassIf(adcs.settlingTime <= 120 [s]);
    }
    // Verification: single-source form
    verification def SettlingCheckSingle {
        subject adcs : ADCS;
        objective { verify req001; }
        return verdict : VerdictKind = PassIf(req001(adcs));
    }
    // REQ-004: real constraint, no verdict binding
    verification def TorqueCheckUnbound {
        subject adcs : ADCS;
        objective { verify req004; }
    }

    verification weakExplicit : SettlingCheckExplicit { subject = weak; }
    verification tunedExplicit : SettlingCheckExplicit { subject = tuned; }
    verification weakSingle : SettlingCheckSingle { subject = weak; }
    verification tunedSingle : SettlingCheckSingle { subject = tuned; }
    verification tunedTorque : TorqueCheckUnbound { subject = tuned; }

    // Human attestation: named satisfy, spec form (typed by the requirement def)
    satisfy requirement attWeak : SettlingReq by weak;
    satisfy requirement attTuned : SettlingReq by tuned;
    not satisfy requirement attWeakNot : SettlingReq by weak;

    // Named satisfy, subsetting form (names the claim, points at the requirement usage)
    satisfy requirement subTuned :> req001 by tuned;
    not satisfy requirement subWeakNot :> req001 by weak;
    // Deliberately contradicting claim: weak does not meet req001
    satisfy requirement subWeakContra :> req001 by weak;

    // Metadata
    metadata statWeak : ModelingMetadata::StatusInfo about attWeak {
        originator = "probe";
        status = StatusKind::done;
    }
    metadata statTuned : ModelingMetadata::StatusInfo about subTuned {
        originator = "probe";
        status = StatusKind::done;
    }
    metadata ratTuned : ModelingMetadata::Rationale about attTuned {
        text = "Model adequate for step response; evidence sufficient.";
        explanation = tunedExplicit;
    }
    // Fallback target: the same status and rationale on the design part itself
    metadata statDesign : ModelingMetadata::StatusInfo about tuned {
        originator = "probe";
        status = StatusKind::tbc;
    }
    metadata ratDesign : ModelingMetadata::Rationale about tuned {
        text = "Adequacy: step-response model is a first-order stand-in. Sufficiency: one run.";
        explanation = tunedSingle;
    }
    metadata execWeak : AnalysisTooling::ToolExecution about weak {
        toolName = "scipy.integrate.solve_ivp";
        uri = "urn:probe:tool:scipy";
    }
    metadata execChain : AnalysisTooling::ToolExecution about tuned::settlingTime {
        toolName = "scipy.integrate.solve_ivp";
        uri = "urn:probe:tool:scipy";
    }
}
