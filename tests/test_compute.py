"""Phase L — compute backend tests.

LocalCompute is exercised live. DockerCompute uses subprocess mocking
so the test doesn't require a running Docker daemon (the live test
against an actual daemon is opt-in below). Also exercises the
provenance-emission path: evidence binding receives an
ExecutionMetadata and emits the expected prov:atLocation +
rtm:hostname / rtm:imageDigest / rtm:containerId triples on the
analysis activity.
"""

from __future__ import annotations

import json
import os
import warnings
from pathlib import Path
from unittest.mock import patch

import pytest
from rdflib import Graph, Literal, URIRef
from rdflib.namespace import RDF

from compute import ExecutionMetadata, get_compute_backend
from compute.base import _local_metadata
from compute.docker_compute import DockerCompute, DockerNotAvailable
from compute.local import LocalCompute
from evidence.binding import _bind_execution_metadata, bind_proof_evidence
from ontology.prefixes import ADCS, PROV, RTM


# ---------------------------------------------------------------------------
# Factory + LocalCompute (live)
# ---------------------------------------------------------------------------

def test_factory_returns_local():
    assert isinstance(get_compute_backend("local"), LocalCompute)


def test_factory_returns_docker():
    assert isinstance(get_compute_backend("docker"), DockerCompute)


def test_factory_rejects_unknown():
    with pytest.raises(ValueError, match="Unknown compute backend"):
        get_compute_backend("not-a-backend")


class TestContainerEntity:
    """WP4 c5 — rtm:DockerContainer entity emission via ExecutionMetadata."""

    def test_container_uri_returns_none_for_local(self):
        from compute.base import ExecutionMetadata
        m = ExecutionMetadata(location_kind="local", hostname="myhost")
        assert m.container_uri() is None

    def test_container_uri_returns_none_when_no_container_id(self):
        from compute.base import ExecutionMetadata
        m = ExecutionMetadata(location_kind="docker", hostname="myhost", container_id="")
        assert m.container_uri() is None

    def test_container_uri_shape_for_docker(self):
        from compute.base import ExecutionMetadata
        m = ExecutionMetadata(location_kind="docker", hostname="myhost", container_id="abc123")
        assert str(m.container_uri()) == "urn:adcs:docker-container:abc123"

    def test_bind_execution_metadata_emits_container_entity(self):
        """When metadata has a container, _bind_execution_metadata
        emits rtm:DockerContainer + prov:used edge + wasDerivedFrom."""
        from rdflib import Graph, URIRef
        from compute.base import ExecutionMetadata
        from evidence.binding import _bind_execution_metadata
        from ontology.prefixes import PROV, RTM

        g = Graph()
        activity = URIRef("urn:adcs:test/activity-1")
        image = URIRef("urn:adcs:docker-image:sha256-abc")
        meta = ExecutionMetadata(
            location_kind="docker",
            hostname="myhost",
            container_id="def456",
            started_at="2026-05-28T12:00:00+00:00",
            ended_at="2026-05-28T12:00:05+00:00",
        )
        _bind_execution_metadata(g, activity, meta, image_iri=image)

        container = URIRef("urn:adcs:docker-container:def456")
        assert (container, RTM.DockerContainer, None) not in g  # subject is container, not object
        # Container exists with correct type
        types = set(g.objects(container, URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type")))
        assert RTM.DockerContainer in types
        assert PROV.Entity in types
        # Container linked to image
        assert (container, PROV.wasDerivedFrom, image) in g
        # Activity used the container
        assert (activity, PROV.used, container) in g
        # Container ID literal
        assert (container, RTM.containerId, None) in g

    def test_bind_execution_metadata_skips_container_for_local(self):
        """Local runs emit NO rtm:DockerContainer node."""
        from rdflib import Graph, URIRef
        from compute.base import ExecutionMetadata
        from evidence.binding import _bind_execution_metadata
        from ontology.prefixes import PROV, RTM

        g = Graph()
        activity = URIRef("urn:adcs:test/activity-2")
        meta = ExecutionMetadata(
            location_kind="local",
            hostname="myhost",
            started_at="2026-05-28T12:00:00+00:00",
            ended_at="2026-05-28T12:00:05+00:00",
        )
        _bind_execution_metadata(g, activity, meta)
        # No rtm:DockerContainer triples anywhere
        assert not list(g.subjects(URIRef("http://www.w3.org/1999/02/22-rdf-syntax-ns#type"), RTM.DockerContainer))

    def test_bind_execution_metadata_org_edges_for_local(self):
        """Local locations carry the compute-substrate auspices: the
        location is operated by the hosting org, the executor acts on
        behalf of the operating org (WP4 c6)."""
        from rdflib import Graph, URIRef
        from compute.base import ExecutionMetadata
        from evidence.binding import _bind_execution_metadata
        from ontology.prefixes import PROV, RTM

        g = Graph()
        activity = URIRef("urn:adcs:test/activity-3")
        operating = URIRef("urn:adcs:org:dynamical-systems-group")
        hosting = URIRef("urn:adcs:org:dynamical-systems-group")
        meta = ExecutionMetadata(location_kind="local", hostname="myhost")
        _bind_execution_metadata(
            g, activity, meta,
            operating_org_iri=operating, hosting_org_iri=hosting,
        )
        location = meta.location_uri()
        executor = meta.executor_uri()
        assert (location, RTM.operatedBy, hosting) in g
        assert (executor, PROV.actedOnBehalfOf, operating) in g


class TestImageNodeEmitsGitRef:
    """WP4 c3 — emit_image_node attaches rtm:gitRef to the rtm:DockerImage."""

    def test_emit_image_node_includes_git_ref_triple(self, monkeypatch, tmp_path):
        """Stubbing _image_metadata so the test doesn't need a Docker daemon,
        verify the image-node emission attaches the rtm:gitRef literal."""
        from rdflib import Graph
        from compute.docker_compute import DockerCompute
        from ontology.prefixes import RTM

        backend = DockerCompute(build_on_demand=False)
        # Skip docker subprocess; pretend image already inspected
        monkeypatch.setattr(
            backend, "_image_metadata",
            lambda: ("sha256:abc123", "adcs-compute:latest"),
        )
        monkeypatch.setattr(
            backend, "_resolve_base_image_digest", lambda: "",
        )
        backend._image_built_at = "2026-05-28T12:00:00+00:00"

        g = Graph()
        iri = backend.emit_image_node(g)

        # The git-ref triple must be present
        git_refs = list(g.objects(iri, RTM.gitRef))
        assert len(git_refs) == 1, f"expected one rtm:gitRef triple, got {len(git_refs)}"
        ref = str(git_refs[0])
        assert ref.startswith("git+"), f"expected git+ URI, got {ref!r}"
        assert "#compute/Dockerfile" in ref, ref


class TestGitRef:
    """WP4 c3 — compute.git_ref captures git+URI shape for rtm:gitRef."""

    def test_current_git_ref_returns_https_uri_in_real_repo(self, tmp_path):
        """Inside the project repo, the URI is the https form with sha + path."""
        from pathlib import Path
        from compute.git_ref import current_git_ref
        repo_root = Path(__file__).resolve().parent.parent
        ref = current_git_ref(repo_root, file_path="compute/Dockerfile")
        # Either https remote (DynamicalSystemsGroup) or file:// fallback;
        # both must include a SHA and the path fragment.
        assert ref.startswith("git+"), f"unexpected shape: {ref}"
        assert "@" in ref and "#compute/Dockerfile" in ref, ref

    def test_current_git_ref_falls_back_outside_git(self, tmp_path):
        """Outside a git repo, fall back to git+local://unknown@uncommitted."""
        from compute.git_ref import current_git_ref
        ref = current_git_ref(tmp_path, file_path="compute/Dockerfile")
        assert "uncommitted" in ref or ref.startswith("git+file://"), ref

    def test_normalize_ssh_remote_to_https(self):
        """git@github.com:Org/Repo.git -> https://github.com/Org/Repo"""
        from compute.git_ref import _normalize_remote_url
        assert _normalize_remote_url("git@github.com:Org/Repo.git") == "https://github.com/Org/Repo"
        assert _normalize_remote_url("https://github.com/Org/Repo.git") == "https://github.com/Org/Repo"


class TestComputeProbe:
    """WP4 c2 — ComputeBackend.probe() preflight."""

    def test_local_compute_probe_is_noop(self):
        LocalCompute().probe()  # must not raise

    def test_docker_not_available_is_compute_unavailable(self):
        """WP4: DockerNotAvailable subclasses ComputeUnavailable so the
        preflight gate can catch the broader type uniformly."""
        from compute.base import ComputeUnavailable
        assert issubclass(DockerNotAvailable, ComputeUnavailable)

    def test_docker_probe_raises_when_daemon_missing(self):
        """DockerCompute.probe wraps _check_daemon; raises when docker absent."""
        backend = DockerCompute(docker_cmd="docker-does-not-exist")
        with pytest.raises(DockerNotAvailable):
            backend.probe()


class TestExecutionMetadataURIs:
    """ExecutionMetadata.executor_uri / location_uri — §4.3 of WP1.

    The IRI shapes are preserved byte-for-byte from the prior
    evidence/binding.py construction so the runtime RDF output does
    not drift.
    """

    def test_executor_uri_prefers_container_id(self):
        md = ExecutionMetadata(
            location_kind="docker", hostname="myhost", container_id="abc123",
        )
        assert str(md.executor_uri()) == "urn:adcs:executor:abc123"

    def test_executor_uri_falls_back_to_hostname(self):
        md = ExecutionMetadata(location_kind="local", hostname="myhost")
        assert str(md.executor_uri()) == "urn:adcs:executor:myhost"

    def test_executor_uri_unknown_when_no_identity(self):
        md = ExecutionMetadata(location_kind="local", hostname="")
        assert str(md.executor_uri()) == "urn:adcs:executor:unknown"

    def test_executor_uri_replaces_colons(self):
        """container_id may contain colons from a digest; URN keeps clean."""
        md = ExecutionMetadata(
            location_kind="docker", hostname="h", container_id="sha256:71a59f23",
        )
        assert str(md.executor_uri()) == "urn:adcs:executor:sha256-71a59f23"

    def test_location_uri_shape(self):
        md = ExecutionMetadata(location_kind="docker", hostname="myhost")
        assert str(md.location_uri()) == "urn:adcs:location:docker:myhost"

    def test_location_uri_unknown_host(self):
        md = ExecutionMetadata(location_kind="local", hostname="")
        assert str(md.location_uri()) == "urn:adcs:location:local:unknown"


def test_local_compute_runs_and_returns_metadata():
    """LocalCompute returns an ExecutionMetadata stamped with local
    hostname and Python version."""
    from analysis.load_params import load_params, load_structural_graph
    sg = load_structural_graph()
    params = load_params(sg)

    backend = LocalCompute()
    result, metadata = backend.run_symbolic_analysis(params)
    assert result is not None
    assert metadata.location_kind == "local"
    assert metadata.hostname
    assert metadata.python_version
    assert metadata.started_at and metadata.ended_at


def test_local_compute_describe():
    assert "Local in-process" in LocalCompute().describe()


# ---------------------------------------------------------------------------
# DockerCompute (mocked subprocess)
# ---------------------------------------------------------------------------

class _FakeProc:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _docker_subprocess_factory(image_digest: str, container_id: str,
                                 container_hostname: str,
                                 base_image_digest: str | None = None):
    """Build a subprocess.run replacement that mimics the docker CLI."""
    def fake_run(cmd, *args, **kwargs):
        # `docker info` — daemon check
        if cmd[1:3] == ["info", "--format"]:
            return _FakeProc(returncode=0, stdout="27.4.0\n")
        # `docker image inspect` — digest lookup. The target image is at
        # index 3. WP3 §4.3 introduces a second inspect call (for the
        # FROM-base, e.g. python:3.12-slim) to resolve baseImageDigest.
        # Heuristic: if the target looks like a public registry tag
        # (no `adcs-compute` prefix), treat it as the base image lookup.
        if cmd[1] == "image" and cmd[2] == "inspect":
            target = cmd[3] if len(cmd) > 3 else ""
            is_base_lookup = "adcs-compute" not in target
            if is_base_lookup:
                if base_image_digest is not None:
                    return _FakeProc(returncode=0, stdout=f"{base_image_digest}\n")
                # Unknown base image / not pulled — graceful degrade path.
                return _FakeProc(returncode=1, stderr="Error: No such image\n")
            return _FakeProc(returncode=0, stdout=f"{image_digest}\n")
        # `docker build`
        if cmd[1] == "build":
            return _FakeProc(returncode=0)
        # `docker run` — write the expected results.json
        if cmd[1] == "run":
            # find --cidfile and -v args
            cidfile_path = None
            mount_arg = None
            for i, arg in enumerate(cmd):
                if arg == "--cidfile":
                    cidfile_path = Path(cmd[i + 1])
                if arg == "-v":
                    mount_arg = cmd[i + 1]
            host_dir = Path(mount_arg.split(":")[0]) if mount_arg else None
            if cidfile_path:
                cidfile_path.write_text(container_id)
            if host_dir:
                (host_dir / "results.json").write_text(json.dumps({
                    "hostname": container_hostname,
                    "python_version": "3.12.13",
                    "platform": "Linux-x86_64",
                    "stage": "symbolic",
                    "started_at": "2026-05-14T00:00:00+00:00",
                    "ended_at": "2026-05-14T00:00:05+00:00",
                }))
            return _FakeProc(returncode=0)
        return _FakeProc(returncode=0)
    return fake_run


@pytest.fixture
def params():
    from analysis.load_params import load_params, load_structural_graph
    return load_params(load_structural_graph())


def test_docker_compute_captures_metadata(params, monkeypatch):
    fake_run = _docker_subprocess_factory(
        image_digest="sha256:abc1234567",
        container_id="container-xyz9876543",
        container_hostname="container-xyz9876",
    )
    monkeypatch.setattr("compute.docker_compute.subprocess.run", fake_run)

    backend = DockerCompute(image="adcs-compute:test", build_on_demand=True)
    result, metadata = backend.run_symbolic_analysis(params)

    assert result is not None
    assert metadata.location_kind == "docker"
    assert metadata.image_digest == "sha256:abc1234567"
    assert metadata.image_label == "adcs-compute:test"
    assert metadata.container_id == "container-xy"   # short (12 chars)
    assert metadata.hostname == "container-xyz9876"
    assert metadata.python_version == "3.12.13"


def test_docker_compute_raises_when_daemon_unreachable(params, monkeypatch):
    def fake_run(cmd, *args, **kwargs):
        if cmd[1:3] == ["info", "--format"]:
            return _FakeProc(returncode=1, stderr="Cannot connect to the Docker daemon")
        return _FakeProc(returncode=0)
    monkeypatch.setattr("compute.docker_compute.subprocess.run", fake_run)

    backend = DockerCompute()
    with pytest.raises(DockerNotAvailable, match="daemon not responding"):
        backend.run_symbolic_analysis(params)


def test_docker_compute_describe():
    assert "Docker-emulated" in DockerCompute().describe()


# ---------------------------------------------------------------------------
# WP3: DockerCompute.emit_image_node() — rtm:DockerImage as evidence (AC3)
# ---------------------------------------------------------------------------

class TestDockerImageEmit:
    """emit_image_node() emits one rtm:DockerImage node per WP3 run with
    all six properties + a stable IRI keyed on the runtime digest."""

    def _stage_compute(self, monkeypatch, image_digest, base_digest):
        """Build a DockerCompute with mocked subprocess + a pre-stamped
        build timestamp (so emit_image_node doesn't have to invoke
        `docker build` for the unit test)."""
        fake_run = _docker_subprocess_factory(
            image_digest=image_digest,
            container_id="container-test",
            container_hostname="container-test-host",
            base_image_digest=base_digest,
        )
        monkeypatch.setattr("compute.docker_compute.subprocess.run", fake_run)
        backend = DockerCompute(image="adcs-compute:test", build_on_demand=False)
        backend._image_built_at = "2026-05-28T00:00:00+00:00"
        return backend

    def test_emit_image_node_populates_all_properties(self, monkeypatch):
        from rdflib import Dataset
        backend = self._stage_compute(
            monkeypatch,
            image_digest="sha256:71a59f23f3e9beef",
            base_digest="sha256:basedigest12345",
        )
        ds = Dataset()
        g = ds.graph(URIRef("urn:rtm:test-evidence"))

        iri = backend.emit_image_node(g)

        # IRI shape: urn:adcs:docker-image:<digest-with-dashes>
        assert str(iri).startswith("urn:adcs:docker-image:")
        assert ":" not in str(iri).removeprefix("urn:adcs:docker-image:")

        from ontology.prefixes import PROV, RTM
        from rdflib.namespace import RDF

        assert (iri, RDF.type, RTM.DockerImage) in g
        assert (iri, RDF.type, PROV.Entity) in g
        assert (iri, RTM.contentHash, Literal("sha256:71a59f23f3e9beef")) in g
        assert (iri, RTM.imageLabel, Literal("adcs-compute:test")) in g
        assert (iri, RTM.baseImageDigest, Literal("sha256:basedigest12345")) in g
        # dockerfileHash + buildContextHash come from real hashing — assert
        # they're present, non-empty, 64-char hex strings.
        df_hashes = list(g.objects(iri, RTM.dockerfileHash))
        bc_hashes = list(g.objects(iri, RTM.buildContextHash))
        assert len(df_hashes) == 1 and len(str(df_hashes[0])) == 64
        assert len(bc_hashes) == 1 and len(str(bc_hashes[0])) == 64
        # generatedAtTime stamped from _image_built_at
        gen_times = list(g.objects(iri, PROV.generatedAtTime))
        assert len(gen_times) == 1
        assert "2026-05-28" in str(gen_times[0])

    def test_emit_image_node_is_idempotent_within_one_run(self, monkeypatch):
        from rdflib import Dataset
        backend = self._stage_compute(
            monkeypatch,
            image_digest="sha256:idempotent",
            base_digest="sha256:base",
        )
        ds = Dataset()
        g = ds.graph(URIRef("urn:rtm:test-evidence"))

        iri1 = backend.emit_image_node(g)
        triples_after_first = len(list(g.triples((iri1, None, None))))
        iri2 = backend.emit_image_node(g)

        assert iri1 == iri2
        # Second call should NOT add more triples (cached return).
        triples_after_second = len(list(g.triples((iri1, None, None))))
        assert triples_after_first == triples_after_second

    def test_emit_image_node_falls_back_to_empty_when_base_image_missing(self, monkeypatch):
        """If the FROM image isn't pulled locally, baseImageDigest is
        omitted rather than failing the pipeline."""
        from rdflib import Dataset
        backend = self._stage_compute(
            monkeypatch,
            image_digest="sha256:no-base",
            base_digest=None,  # docker image inspect returns rc=1 for the base
        )
        ds = Dataset()
        g = ds.graph(URIRef("urn:rtm:test-evidence"))

        iri = backend.emit_image_node(g)

        from ontology.prefixes import RTM
        # contentHash still present (project image was found)
        assert (iri, RTM.contentHash, Literal("sha256:no-base")) in g
        # baseImageDigest absent (graceful degrade)
        assert list(g.objects(iri, RTM.baseImageDigest)) == []

    def test_emit_image_node_iri_uses_dashes_for_colons(self, monkeypatch):
        """IRI suffix must escape colons so the urn: parses cleanly."""
        from rdflib import Dataset
        backend = self._stage_compute(
            monkeypatch,
            image_digest="sha256:abc:def",  # extra colon, paranoid case
            base_digest="sha256:base",
        )
        ds = Dataset()
        g = ds.graph(URIRef("urn:rtm:test-evidence"))

        iri = backend.emit_image_node(g)

        assert ":" not in str(iri).removeprefix("urn:adcs:docker-image:")
        assert "sha256-abc-def" in str(iri)


def _parse_from_smoke():
    """Sanity: the real compute/Dockerfile's FROM line is parseable."""
    backend = DockerCompute(image="adcs-compute:test", build_on_demand=False)
    base = backend._parse_from_image()
    # Current Dockerfile uses python:3.12-slim; we don't pin the
    # version in the assertion (the demo may bump it) — just confirm
    # the parser returns something that looks like a python image.
    assert "python" in base, f"Could not parse FROM image; got: {base!r}"


def test_dockerfile_from_line_parseable():
    _parse_from_smoke()


# ---------------------------------------------------------------------------
# Provenance emission — _bind_execution_metadata side
# ---------------------------------------------------------------------------

def test_bind_execution_metadata_emits_location_and_executor():
    """Given a synthetic ExecutionMetadata, the evidence-binding helper
    emits the expected PROV triples on the analysis activity."""
    g = Graph()
    activity = ADCS["SA-TEST"]
    metadata = ExecutionMetadata(
        location_kind="docker",
        hostname="container-abc123",
        image_digest="sha256:deadbeef",
        image_label="adcs-compute:latest",
        container_id="abc123def456",
        python_version="3.12.13",
        started_at="2026-05-14T00:00:00+00:00",
        ended_at="2026-05-14T00:00:05+00:00",
    )
    _bind_execution_metadata(g, activity, metadata)

    # prov:atLocation -> a typed Location
    locations = list(g.objects(activity, PROV.atLocation))
    assert len(locations) == 1
    assert (locations[0], RDF.type, PROV.Location) in g

    # prov:wasAssociatedWith -> a SoftwareAgent executor
    executors = list(g.objects(activity, PROV.wasAssociatedWith))
    assert executors
    executor = executors[0]
    assert (executor, RDF.type, PROV.SoftwareAgent) in g

    # Executor carries the metadata as RTM triples
    assert (executor, RTM.hostname, Literal("container-abc123")) in g
    assert (executor, RTM.imageDigest, Literal("sha256:deadbeef")) in g
    assert (executor, RTM.imageLabel, Literal("adcs-compute:latest")) in g
    assert (executor, RTM.containerId, Literal("abc123def456")) in g
    assert (executor, RTM.pythonVersion, Literal("3.12.13")) in g


def test_bind_execution_metadata_handles_none():
    """No-op when execution_metadata=None — keeps the local-compute path
    (without explicit metadata propagation) viable."""
    g = Graph()
    activity = ADCS["SA-TEST"]
    _bind_execution_metadata(g, activity, None)
    # No triples should be added
    assert len(g) == 0


def test_bind_proof_evidence_forwards_metadata_to_activity():
    """End-to-end: bind_proof_evidence with a metadata arg should leave
    PROV-O triples on the analysis activity describing the executor."""
    g = Graph()
    bind_proof_evidence(
        g,
        evidence_id="EV-PROOF-TEST",
        activity_id="SA-TEST",
        requirement_id="REQ-TEST",
        model_hash="m",
        proof_hash="p",
        content_hash="c",
        result_summary="test summary",
        execution_metadata=ExecutionMetadata(
            location_kind="docker",
            hostname="container-xyz",
            image_digest="sha256:abc",
            container_id="xyz123abc456",
        ),
    )
    activity = ADCS["SA-TEST"]
    locations = list(g.objects(activity, PROV.atLocation))
    assert locations, "expected prov:atLocation on the SA-TEST activity"
    executors = [
        e for e in g.objects(activity, PROV.wasAssociatedWith)
        if (e, RDF.type, PROV.SoftwareAgent) in g
    ]
    assert executors, "expected a prov:SoftwareAgent executor on SA-TEST"


# ---------------------------------------------------------------------------
# Live test (opt-in)
# ---------------------------------------------------------------------------

def _docker_daemon_up() -> bool:
    """Quick check that `docker info` succeeds."""
    import subprocess
    try:
        proc = subprocess.run(
            ["docker", "info", "--format", "{{.ServerVersion}}"],
            capture_output=True, timeout=5,
        )
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


@pytest.mark.skipif(
    not _docker_daemon_up(),
    reason="Docker daemon unavailable; --compute=docker live path requires it",
)
def test_docker_compute_live(params):
    """Live test: actually run a stage inside the container.

    Auto-skips when Docker isn't running. Requires the adcs-compute
    image to exist (built by `docker build -t adcs-compute:latest -f
    compute/Dockerfile .`).
    """
    backend = DockerCompute()
    with warnings.catch_warnings():
        warnings.filterwarnings("ignore", category=DeprecationWarning)
        result, metadata = backend.run_symbolic_analysis(params)
    assert result is not None
    assert metadata.location_kind == "docker"
    assert metadata.image_digest.startswith("sha256:"), (
        f"expected image digest, got {metadata.image_digest!r}"
    )
    assert metadata.container_id, "container_id should be set"
    assert metadata.hostname, "container hostname should be captured"
