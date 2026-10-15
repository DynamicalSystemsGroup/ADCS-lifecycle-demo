// Views over the GeoSatADCS package (sysml/satellite.sysml + the evidence and attestation blocks
// that sysml/model.py splices in). Loaded beside the model; rendered by sysml/views.py and
// scripts/build_tool_assets.py. A view carries no model content, only a scope and a render kind.
package TalkViews {
    private import GeoSatADCS::*;

    // REQ-001 with the verification cases that verify it. A requirement rendering draws the
    // verification cases; the REDK `verdicts` overlay colours the requirement by their verdicts.
    view requirementView : StandardViewDefinitions::GeneralView {
        expose GeoSatADCS::*;
        filter @SysML::RequirementUsage or @SysML::RequirementDefinition;
    }

    // The design's structure: the part def, and the requirement whose subject it is.
    view structureView : StandardViewDefinitions::GeneralView {
        expose GeoSatADCS::ADCS;
        expose GeoSatADCS::SettlingRequirement;
        expose GeoSatADCS::req001;
    }
}
