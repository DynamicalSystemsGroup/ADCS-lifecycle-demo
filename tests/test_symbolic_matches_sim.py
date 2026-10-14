"""Regression: the symbolic stiffness must match the simulation's control law.

The simulation applies -Kp/2 to the quaternion vector part (about theta/2),
so the effective stiffness on theta is Kp/4. The period predicted by the
symbolic characteristic polynomial must match the simulated x-axis period.
"""
import math

import numpy as np
import sympy as sp

from analysis.load_params import load_params
from analysis.numerical import run_step_response
from analysis.symbolic import Jxx, Kd, Kp, characteristic_polynomial_single_axis, evaluate_inertia, s


def _simulated_period(params):
    res = run_step_response(params)
    q0 = res.q[:, 0]
    t = res.t
    idx = np.where(np.sign(q0[:-1]) * np.sign(q0[1:]) < 0)[0]
    # linear-interpolated zero crossings; successive crossings are half a period apart
    tz = [t[i] - q0[i] * (t[i + 1] - t[i]) / (q0[i + 1] - q0[i]) for i in idx]
    assert len(tz) >= 2, "need at least two zero crossings"
    return 2.0 * float(np.mean(np.diff(tz)))


def test_symbolic_period_matches_simulation():
    params = dict(load_params(), Kp=1.0, Kd=10.0)
    J = evaluate_inertia(params)[0]
    poly = characteristic_polynomial_single_axis(Jxx)
    kp_eff = float(sp.Poly(poly, s).coeff_monomial(1).subs({Kp: 1.0, Kd: 10.0}))
    wn = math.sqrt(kp_eff / J)
    zeta = 10.0 / (2.0 * math.sqrt(kp_eff * J))
    assert zeta < 1.0, "x-axis must be underdamped for an oscillation"
    predicted = 2.0 * math.pi / (wn * math.sqrt(1.0 - zeta**2))
    measured = _simulated_period(params)
    assert abs(predicted - measured) / measured < 0.02, (predicted, measured)
