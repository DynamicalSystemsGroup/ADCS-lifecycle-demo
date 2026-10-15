"""The REQ-001 requirement view (sysml/views.py): verdict overlay, palette, and speed."""

import time

import pytest

from sysml import views
from sysml.views import design_model, requirement_view

PASS_FILL, FAIL_FILL = "#99D8C7", "#EEBF99"  # okabe-ito, as REDK fills them


@pytest.fixture(scope="module")
def failing():
    return design_model("initial", 1.0, 10.0, satisfied=False)


@pytest.fixture(scope="module")
def passing():
    return design_model("final", 8.0, 30.0, satisfied=True)


@pytest.fixture(params=["cli", "api"])
def path(request, monkeypatch):
    """Both rendering paths: the REDK CLI (when installed) and the uv-environment API."""
    if request.param == "api":
        monkeypatch.setattr(views, "sysml_cli", lambda: None)
    elif views.sysml_cli() is None:
        pytest.skip("sysml CLI not installed (scripts/fetch_tools.sh)")
    return request.param


def test_failing_design_is_orange_with_its_verdict(path, failing):
    out = requirement_view(failing)
    assert "verdict fail by GeoSatADCS::vc001_initial" in out
    assert FAIL_FILL in out and PASS_FILL not in out


def test_passing_design_is_green_with_its_verdict(path, passing):
    out = requirement_view(passing)
    assert "verdict pass by GeoSatADCS::vc001_final" in out
    assert PASS_FILL in out and FAIL_FILL not in out


def test_view_is_scoped_to_req001_and_its_verification(path, passing):
    out = requirement_view(passing)
    assert "req001 : SettlingRequirement" in out and "SettlingVerification" in out
    assert "Kp" not in out  # no part-def attributes: the view is not the structure


def test_attestation_is_not_drawn(path, failing, passing):
    """Verdicts are verification; the engineer's claim does not recolour the requirement."""
    flipped = passing.replace("    satisfy requirement", "    not satisfy requirement", 1)
    assert flipped != passing
    assert requirement_view(flipped) == requirement_view(passing)


def test_requirement_view_is_fast(path, passing):
    t0 = time.perf_counter()
    requirement_view(passing)
    assert time.perf_counter() - t0 < 5


def test_other_forms_need_the_cli(monkeypatch, passing):
    monkeypatch.setattr(views, "sysml_cli", lambda: None)
    with pytest.raises(RuntimeError, match="needs the sysml CLI"):
        requirement_view(passing, form="plantuml")


def test_unknown_form_is_refused(passing):
    with pytest.raises(ValueError):
        views.render_view(passing, views.REQUIREMENT_VIEW, form="svg")
