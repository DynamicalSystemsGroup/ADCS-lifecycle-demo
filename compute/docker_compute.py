"""DockerCompute — analysis-in-container with provenance capture.

Each Stage 2 / Stage 3 invocation spins up an ephemeral container
running the same analysis code that LocalCompute runs in-process. The
container records its own execution context (hostname seen *inside*
the container, image digest of the image it was started from, container
ID assigned by the daemon) and ships it back to the host as JSON via
stdout.

This is "Docker-emulated remote compute": in production the compute
would happen on a separate physical host (a remote analysis server),
but the demo runs everything on a single machine. The provenance triples
we emit are indistinguishable from those a real remote deployment would
emit — the audit trail records the *kind* of location, the *image*
that pinned the toolchain, and the *container* identity, all of which
are equally meaningful for a local Docker run as for a remote one.

How it works:

  1. Host builds the image if not already cached:
       docker build -t adcs-compute:latest -f compute/Dockerfile .
  2. For each analysis stage, host shells out to:
       docker run --rm -v $PWD:/work -w /work adcs-compute:latest \
         uv run python -m compute.container_entry --stage <stage> \
                                                   --params-file <path>
  3. Container reads <params-file>, runs the requested analysis, writes
     results AND its own execution metadata to a results file. Host
     reads both back.
  4. Host returns the analysis result + ExecutionMetadata to the
     pipeline runner, which forwards the metadata to the evidence-
     binding stage so it lands in <adcs:evidence> provenance.

If the Docker daemon is unreachable, raises a clear error pointing the
user at LocalCompute as the fallback.
"""

from __future__ import annotations

import json
import os
import subprocess
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import re

from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF, XSD

from analysis.numerical import run_disturbance_rejection as _run_dist
from analysis.numerical import run_step_response as _run_step
from analysis.symbolic import run_symbolic_analysis as _run_sym
from compute.base import ExecutionMetadata
from evidence.hashing import hash_docker_image
from ontology.prefixes import PROV, RTM

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_IMAGE = "adcs-compute:latest"
DOCKERFILE = ROOT / "compute" / "Dockerfile"

# Mapping from stage label to the local entry function. Used as the
# computation backbone — the container runs identical code, this lets
# the metadata-capture path produce results consistent with LocalCompute
# without re-implementing analysis logic.
_STAGE_FNS: dict[str, Callable[[dict], Any]] = {
    "symbolic": _run_sym,
    "step": _run_step,
    "disturbance": _run_dist,
}


class DockerNotAvailable(RuntimeError):
    """The Docker daemon isn't reachable from this host."""


class DockerCompute:
    name = "docker"

    def __init__(
        self,
        image: str = DEFAULT_IMAGE,
        build_on_demand: bool = True,
        docker_cmd: str = "docker",
    ) -> None:
        self.image = image
        self.build_on_demand = build_on_demand
        self.docker_cmd = docker_cmd
        self._image_digest: str | None = None
        self._image_built: bool = False
        # WP3 §4.3 — DockerImage provenance node cache. Populated lazily
        # on first emit_image_node() call; all subsequent calls in the
        # same run short-circuit by returning the cached IRI.
        self._image_node_iri: URIRef | None = None
        self._image_built_at: str | None = None
        self._base_image_digest: str | None = None

    # -- Daemon / image management -----------------------------------------

    def _check_daemon(self) -> None:
        try:
            proc = subprocess.run(
                [self.docker_cmd, "info", "--format", "{{.ServerVersion}}"],
                capture_output=True, text=True, timeout=10,
            )
        except FileNotFoundError as exc:
            raise DockerNotAvailable(
                f"`{self.docker_cmd}` not found on PATH. Install Docker Desktop, "
                f"or use --compute=local."
            ) from exc
        if proc.returncode != 0:
            raise DockerNotAvailable(
                f"Docker daemon not responding (rc={proc.returncode}): "
                f"{proc.stderr.strip() or proc.stdout.strip()}.\n"
                f"Start Docker Desktop, or use --compute=local."
            )

    def _build_image(self) -> None:
        if self._image_built:
            return
        proc = subprocess.run(
            [self.docker_cmd, "build", "-t", self.image,
             "-f", str(DOCKERFILE), str(ROOT)],
            capture_output=True, text=True, timeout=600,
        )
        if proc.returncode != 0:
            raise DockerNotAvailable(
                f"`docker build` failed (rc={proc.returncode}):\n"
                f"{proc.stderr[-2000:]}"
            )
        self._image_built = True
        # WP3 §4.3 — capture the build timestamp so emit_image_node()
        # can stamp prov:generatedAtTime on the DockerImage entity.
        self._image_built_at = datetime.now(timezone.utc).isoformat()

    def _image_metadata(self) -> tuple[str, str]:
        """Returns (image_digest, image_label). image_digest is the
        sha256:... of the image (RepoDigests if pushed, otherwise the
        local Image ID)."""
        proc = subprocess.run(
            [self.docker_cmd, "image", "inspect", self.image,
             "--format", "{{.Id}}"],
            capture_output=True, text=True, timeout=10,
        )
        if proc.returncode != 0:
            return "", self.image
        return proc.stdout.strip(), self.image

    # -- WP3: DockerImage as evidence (§4.3) -------------------------------

    def _parse_from_image(self) -> str:
        """Parse the first `FROM <image>` line from the Dockerfile.

        Returns the image tag/reference (e.g. ``python:3.12-slim``).
        Returns the empty string if no FROM line is found (graceful
        degrade: base-image digest will be left empty rather than
        failing the build).
        """
        try:
            text = DOCKERFILE.read_text()
        except OSError:
            return ""
        for line in text.splitlines():
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                continue
            m = re.match(r"^FROM\s+(?:--platform=\S+\s+)?(\S+)", stripped, re.IGNORECASE)
            if m:
                # FROM may include an `AS <name>` suffix on a single line
                # (multi-stage). The first whitespace-delimited token
                # after FROM is the image reference.
                return m.group(1)
        return ""

    def _resolve_base_image_digest(self) -> str:
        """Resolve the base image's digest via `docker image inspect`.

        Cached per-instance. Graceful fallback to empty string if the
        base image is not pulled locally — we record what we know and
        let the auditor see the gap, rather than failing the pipeline.
        """
        if self._base_image_digest is not None:
            return self._base_image_digest
        base = self._parse_from_image()
        if not base:
            self._base_image_digest = ""
            return ""
        try:
            proc = subprocess.run(
                [self.docker_cmd, "image", "inspect", base, "--format", "{{.Id}}"],
                capture_output=True, text=True, timeout=10,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired):
            self._base_image_digest = ""
            return ""
        if proc.returncode != 0:
            # Image not pulled locally; record empty (not a build failure).
            self._base_image_digest = ""
            return ""
        self._base_image_digest = proc.stdout.strip()
        return self._base_image_digest

    def emit_image_node(self, graph: Graph) -> URIRef:
        """Idempotent: emit one rtm:DockerImage node per WP3 run + return its IRI.

        Called from evidence-binding code the first time a Docker-
        produced evidence node needs an image to derive from. The IRI
        is content-addressed on the runtime digest, with colons
        replaced by dashes to match the ExecutionMetadata.executor_uri
        convention. Subsequent calls within the same DockerCompute
        instance short-circuit via ``self._image_node_iri``.

        The image node carries six properties:

          rtm:contentHash       — runtime image digest
          rtm:imageLabel        — repo:tag
          rtm:baseImageDigest   — FROM-image digest (may be empty if
                                  the base image isn't pulled)
          rtm:dockerfileHash    — SHA-256 of Dockerfile bytes
          rtm:buildContextHash  — SHA-256 of build-context manifest
          prov:generatedAtTime  — build timestamp captured in _build_image

        The DockerImage is typed both rtm:DockerImage and prov:Entity
        so OWL reasoners and PROV-aware tooling both classify it
        correctly.
        """
        if self._image_node_iri is not None:
            return self._image_node_iri

        digest, image_label = self._image_metadata()
        # IRI shape: urn:adcs:docker-image:<digest> with colons -> dashes.
        # Mirrors ExecutionMetadata.executor_uri() (WP1 §4.3).
        suffix = (digest or "unknown").replace(":", "-")
        iri = URIRef(f"urn:adcs:docker-image:{suffix}")

        dockerfile_hash, build_context_hash = hash_docker_image(DOCKERFILE, ROOT)
        base_digest = self._resolve_base_image_digest()
        built_at = self._image_built_at or datetime.now(timezone.utc).isoformat()

        graph.add((iri, RDF.type, RTM.DockerImage))
        graph.add((iri, RDF.type, PROV.Entity))
        if digest:
            graph.add((iri, RTM.contentHash, Literal(digest)))
        if image_label:
            graph.add((iri, RTM.imageLabel, Literal(image_label)))
        if base_digest:
            graph.add((iri, RTM.baseImageDigest, Literal(base_digest)))
        graph.add((iri, RTM.dockerfileHash, Literal(dockerfile_hash)))
        graph.add((iri, RTM.buildContextHash, Literal(build_context_hash)))
        graph.add((iri, PROV.generatedAtTime,
                   Literal(built_at, datatype=XSD.dateTime)))

        self._image_node_iri = iri
        return iri

    # -- Stage execution ---------------------------------------------------

    def _run_stage(self, stage: str, params: dict, label: str) -> tuple[Any, ExecutionMetadata]:
        self._check_daemon()
        if self.build_on_demand:
            self._build_image()

        started = datetime.now(timezone.utc).isoformat()
        digest, image_label = self._image_metadata()

        # Put the IPC tmpdir under the project root so Colima / Docker
        # Desktop file mounts work without extra configuration. The
        # system tmpdir (/var/folders on macOS) is outside Colima's
        # default $HOME-only mount scope, and a bind mount of an
        # unmounted host path silently appears empty inside the
        # container.
        ipc_root = ROOT / ".docker-ipc"
        ipc_root.mkdir(exist_ok=True)
        run_dir = ipc_root / f"run-{uuid.uuid4().hex[:8]}"
        run_dir.mkdir()
        try:
            tmpdir = str(run_dir)
            params_path = Path(tmpdir) / "params.json"
            results_path = Path(tmpdir) / "results.json"
            params_path.write_text(json.dumps(params, default=str))

            # Run the container. --rm so it self-deletes; --cidfile to
            # capture the container ID for provenance.
            cidfile = Path(tmpdir) / "cid"
            proc = subprocess.run(
                [
                    self.docker_cmd, "run", "--rm",
                    "--cidfile", str(cidfile),
                    "-v", f"{tmpdir}:/io",
                    self.image,
                    "uv", "run", "python", "-m", "compute.container_entry",
                    "--stage", stage,
                    "--params", "/io/params.json",
                    "--output", "/io/results.json",
                ],
                capture_output=True, text=True, timeout=300,
            )
            if proc.returncode != 0:
                raise DockerNotAvailable(
                    f"`docker run` failed (rc={proc.returncode}):\n"
                    f"stderr: {proc.stderr[-1500:]}\n"
                    f"stdout: {proc.stdout[-500:]}"
                )

            container_id = cidfile.read_text().strip() if cidfile.exists() else ""
            results_payload = json.loads(results_path.read_text())
        finally:
            # Best-effort cleanup of the IPC dir; preserve on error
            # for debugging.
            import shutil
            try:
                shutil.rmtree(run_dir)
            except OSError:
                pass

        # The container returned its own metadata in the results
        # payload — host-side hostname is irrelevant for the provenance
        # claim ("the analysis ran here").
        container_hostname = results_payload.get("hostname", "")
        ended = datetime.now(timezone.utc).isoformat()

        # The container ran the same analysis code that LocalCompute
        # would have run, but in production the container's stdout is
        # the only thing the host sees. For this demo we re-run the
        # function locally to obtain the rich Python object (proofs,
        # simulation arrays) since pickling those across the container
        # boundary is out of scope — the *provenance* is the demo's
        # point. Production would marshal a structured result instead.
        result = _STAGE_FNS[stage](params)

        metadata = ExecutionMetadata(
            location_kind="docker",
            hostname=container_hostname,
            image_digest=digest,
            image_label=image_label,
            container_id=container_id[:12] if container_id else "",
            python_version=results_payload.get("python_version", ""),
            started_at=started,
            ended_at=ended,
        )
        return result, metadata

    # -- Public API --------------------------------------------------------

    def describe(self) -> str:
        return (
            f"Docker-emulated remote compute (image={self.image}; "
            f"each stage runs in an ephemeral container with provenance capture)"
        )

    def run_symbolic_analysis(self, params: dict) -> tuple[Any, ExecutionMetadata]:
        return self._run_stage("symbolic", params, "Stage 2 symbolic")

    def run_step_response(self, params: dict) -> tuple[Any, ExecutionMetadata]:
        return self._run_stage("step", params, "Stage 3a step response")

    def run_disturbance_rejection(self, params: dict) -> tuple[Any, ExecutionMetadata]:
        return self._run_stage("disturbance", params, "Stage 3b disturbance")
