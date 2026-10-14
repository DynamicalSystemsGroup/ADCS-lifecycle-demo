// GeoSatADCS: structure block. Hand-authored, static, lives in Git.
// Evidence and attestation blocks are spliced in before the closing brace by sysml/model.py.
package GeoSatADCS {
    private import ScalarValues::*;
    private import ISQ::*;
    private import SI::*;
    private import VerificationCases::*;
    private import ModelingMetadata::*;
    private import AnalysisTooling::*;

    part def ADCS {
        attribute Kp : Real;
        attribute Kd : Real;
        attribute settlingTime : ISQ::DurationValue;
        attribute peakTorque : ISQ::TorqueValue;
        attribute torqueLimit : ISQ::TorqueValue;
    }

    // REQ-001. The doc text is the sysml:text of structural/satellite.ttl, word for word.
    // The constraint encodes only the 120 s clause of that text.
    requirement def SettlingRequirement {
        doc /* The ADCS shall maintain pointing accuracy within 0.1 degrees
        (3-sigma) under nominal disturbance conditions within 120 seconds
        of a slew maneuver. */
        subject adcs : ADCS;
        require constraint { adcs.settlingTime <= 120 [s] }
    }
    requirement req001 : SettlingRequirement;

    // REQ-004. The constraint encodes the "without exceeding actuator torque capacity" clause.
    requirement def DisturbanceRequirement {
        doc /* The ADCS shall reject gravity gradient disturbance torques
        encountered in geostationary orbit without exceeding actuator
        torque capacity. */
        subject adcs : ADCS;
        require constraint { adcs.peakTorque <= adcs.torqueLimit }
    }
    requirement req004 : DisturbanceRequirement;

    // REQ-001: the case declares a verdict, computed from req001 itself.
    verification def SettlingVerification {
        subject adcs : ADCS;
        objective { verify req001; }
        metadata VerificationMethod { kind = VerificationMethodKind::analyze; }
        return verdict : VerdictKind = PassIf(req001(adcs));
    }

    // REQ-004: no verdict binding, by design (ACE-04). The result is inconclusive.
    verification def DisturbanceVerification {
        subject adcs : ADCS;
        objective { verify req004; }
        metadata VerificationMethod { kind = VerificationMethodKind::analyze; }
    }
}
