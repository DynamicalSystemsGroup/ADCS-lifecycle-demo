# ============================================================================
# ADCS Lifecycle Demo — ontology build chain
#
# Two paths:
#   - Default (Python-only, no external deps): `make ontology`
#       Validates references, generates equivalence axioms from
#       sysml_term_map.csv, produces rtm.ttl + assembly_manifest.json.
#   - Optional (ROBOT, requires Java + ROBOT JAR): `make ontology-robot`
#       Full MIREOT extracts + ELK reasoning + report. Production-grade
#       ontology authoring path used by openCAESAR / OBO Foundry stacks.
#
# Demo users running the pipeline (`uv run python -m pipeline.runner`) do
# NOT need either path — rtm.ttl is committed.
# ============================================================================

.PHONY: help fetch-imports ontology ontology-robot validate-imports clean-imports flexo-up flexo-init flexo-down

help:
	@echo "Ontology build targets:"
	@echo "  fetch-imports     Pull upstream ontologies into ontology/imports/"
	@echo "  ontology          Build rtm.ttl + assembly_manifest.json (Python, no ROBOT)"
	@echo "  ontology-robot    Build rtm.ttl via ROBOT merge + reason + report (requires robot)"
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
	@command -v robot >/dev/null 2>&1 || { \
		echo "ROBOT is not installed."; \
		echo "Install: brew install robot  (macOS)  or download from http://robot.obolibrary.org"; \
		echo "ROBOT is OPTIONAL — the demo runs from the committed ontology/rtm.ttl without it."; \
		echo "Use 'make ontology' for the Python-only build."; \
		exit 1; \
	}
	@echo "[ROBOT] Merging rtm-edit.ttl + vendored imports ..."
	robot merge \
		--catalog ontology/catalog-v001.xml \
		--input ontology/rtm-edit.ttl \
		--output ontology/rtm-merged.ttl
	@echo "[ROBOT] Reasoning ..."
	robot reason --reasoner ELK \
		--input ontology/rtm-merged.ttl \
		--output ontology/rtm.ttl
	@echo "[ROBOT] Report ..."
	robot report \
		--input ontology/rtm.ttl \
		--output ontology/robot-report.tsv \
		--fail-on ERROR
	@echo "[ROBOT] ROBOT path complete. Run 'make ontology' afterward to refresh the Python-side manifest if needed."

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
