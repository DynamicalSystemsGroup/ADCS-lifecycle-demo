# =============================================================================
# Compute container for the ADCS lifecycle demo.
#
# Emulates a remote execution server where Stage 2 (symbolic analysis) and
# Stage 3 (numerical simulation) would run in a production deployment.
# Captures execution metadata (hostname, image digest, container ID) into
# RTM provenance so the resulting attestations record WHERE and HOW each
# piece of evidence was produced — a load-bearing requirement when the
# engineer's machine and the compute server are different physical hosts.
#
# Build (one-time, by host orchestrator):
#   docker build -t adcs-compute:latest -f compute/Dockerfile .
#
# Run (driven by --compute=docker on the pipeline):
#   docker run --rm \
#     -v $(pwd):/work \
#     -w /work \
#     adcs-compute:latest \
#     uv run python -m compute.container_entry --stage symbolic
# =============================================================================

FROM python:3.12-slim

# System dependencies. scipy needs a few small native libs.
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        gcc g++ gfortran libopenblas-dev liblapack-dev && \
    rm -rf /var/lib/apt/lists/*

# uv (matches host toolchain)
RUN pip install --no-cache-dir uv==0.5.4

WORKDIR /work

# Copy only what the analysis stages need (keeps the image small and
# avoids cache invalidation on unrelated edits).
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-dev

# Copy the analysis and evidence packages plus their dependencies.
COPY analysis/ ./analysis/
COPY ontology/ ./ontology/
COPY structural/ ./structural/
COPY evidence/ ./evidence/
COPY compute/ ./compute/

# Image label: read at runtime by container_entry to confirm we are
# inside the expected image.
LABEL org.adcs-demo.role="compute"
LABEL org.adcs-demo.stage="analysis"

# Default to a no-op so the container is safe to inspect interactively.
CMD ["uv", "run", "python", "-m", "compute.container_entry", "--describe"]
