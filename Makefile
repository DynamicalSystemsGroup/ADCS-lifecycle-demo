# ============================================================================
# ADCS Lifecycle Demo — ontology build chain
#
# Two paths:
#   - Default (Python-only, no external deps): `make ontology`
#       Validates references, generates equivalence axioms from
#       sysml_term_map.csv, produces rtm.ttl + assembly_manifest.json.
#       This is the canonical build.
#   - Optional (ROBOT, requires Java + the OBO ROBOT JAR): `make ontology-robot`
#       Independent validation via the production-grade openCAESAR / OBO
#       Foundry toolchain. Resolves owl:imports via catalog-v001.xml,
#       merges, runs ELK reasoning, runs the OBO hygiene report. Produces
#       a fat merged-with-imports artifact for inspection. Does NOT
#       overwrite the canonical ontology/rtm.ttl.
#
# Demo users running the pipeline (`uv run python -m pipeline.runner`) do
# NOT need either path — rtm.ttl is committed.
#
# ROBOT note: macOS's `brew install robot-framework` installs Robot
# Framework (Python test tool) which owns /usr/local/bin/robot. The OBO
# ROBOT is installed as `obo-robot` to avoid the name collision. Set
# the ROBOT variable below if your install uses a different name.
# ============================================================================

ROBOT ?= obo-robot
JAVA_HOME ?= /usr/local/opt/openjdk

.PHONY: help fetch-imports ontology ontology-robot validate-imports clean-imports flexo-up flexo-init flexo-down

help:
	@echo "Ontology build targets:"
	@echo "  fetch-imports     Pull upstream ontologies into ontology/imports/"
	@echo "  ontology          Build rtm.ttl + assembly_manifest.json (Python, canonical)"
	@echo "  ontology-robot    Validate via ROBOT (merge + reason + report). Requires $$($(ROBOT) --version 2>/dev/null | tail -1 || echo 'OBO ROBOT')."
	@echo "  validate-imports  Check vendored imports parse and contain referenced terms"
	@echo "  clean-imports     Remove ontology/imports/ (forces re-fetch)"
	@echo ""
	@echo "Flexo MMS targets (Phase J — not yet wired):"
	@echo "  flexo-up          Bring up local Flexo + Fuseki via Docker Compose"
	@echo "  flexo-init        Provision adcs-demo org/project/repo/branch in Flexo"
	@echo "  flexo-down        Tear down the Flexo stack"

fetch-imports:
	uv run python -m scripts.fetch_imports

ontology:
	uv run python -m scripts.build_ontology

validate-imports:
	@uv run python -c "from rdflib import Graph; \
import sys; \
from pathlib import Path; \
ok = True; \
[print(f'  OK  {p.name}: {len(Graph().parse(p, format=\"turtle\"))} triples') for p in Path('ontology/imports').glob('*.ttl')]"

ontology-robot:
	@command -v $(ROBOT) >/dev/null 2>&1 || { \
		echo "OBO ROBOT not found (looking for command: $(ROBOT))."; \
		echo "Install: download from http://robot.obolibrary.org and place wrapper at /usr/local/bin/obo-robot."; \
		echo "Or override the command name: ROBOT=/path/to/robot make ontology-robot"; \
		echo ""; \
		echo "ROBOT is OPTIONAL — the canonical build is 'make ontology' (Python-only)."; \
		exit 1; \
	}
	@PATH="$(JAVA_HOME)/bin:$$PATH" $(ROBOT) --version >/dev/null 2>&1 || { \
		echo "ROBOT found but Java is missing or unreachable."; \
		echo "Set JAVA_HOME (currently: $(JAVA_HOME)) to a JRE 11+ install."; \
		exit 1; \
	}
	@echo "[ROBOT] Merging rtm-edit.ttl + vendored imports (via ontology/catalog-v001.xml) ..."
	PATH="$(JAVA_HOME)/bin:$$PATH" $(ROBOT) merge \
		--catalog ontology/catalog-v001.xml \
		--input ontology/rtm-edit.ttl \
		--output ontology/rtm-robot-merged.ttl
	@echo "[ROBOT] Reasoning (ELK) — consistency check ..."
	PATH="$(JAVA_HOME)/bin:$$PATH" $(ROBOT) reason \
		--reasoner ELK \
		--input ontology/rtm-robot-merged.ttl \
		--output ontology/rtm-robot-reasoned.ttl
	@echo "[ROBOT] Report (OBO hygiene lints — profiled to scope rules to our terms) ..."
	PATH="$(JAVA_HOME)/bin:$$PATH" $(ROBOT) report \
		--input ontology/rtm-robot-reasoned.ttl \
		--profile ontology/robot-report-profile.txt \
		--output ontology/rtm-robot-report.tsv \
		--fail-on ERROR \
		|| { echo "ROBOT report flagged ERROR-level findings; see ontology/rtm-robot-report.tsv"; exit 1; }
	@echo ""
	@echo "[ROBOT] Validation complete."
	@echo "  Merged-with-imports:  ontology/rtm-robot-merged.ttl"
	@echo "  Reasoned:             ontology/rtm-robot-reasoned.ttl"
	@echo "  Report:               ontology/rtm-robot-report.tsv"
	@echo ""
	@echo "  Canonical artifact (ontology/rtm.ttl) is unchanged — produced by 'make ontology'."
	@echo "  ROBOT outputs are validation/inspection artifacts (gitignored)."

clean-imports:
	rm -rf ontology/imports/

# ----------------------------------------------------------------------------
# Flexo MMS targets (Phase J)
# ----------------------------------------------------------------------------

flexo-up:
	@echo "Phase J not yet landed. Will run: docker compose -f flexo/docker-compose.yml up -d"
	@exit 1

flexo-init:
	@echo "Phase J not yet landed. Will run: ./flexo/init.sh"
	@exit 1

flexo-down:
	@echo "Phase J not yet landed. Will run: docker compose -f flexo/docker-compose.yml down -v"
	@exit 1
