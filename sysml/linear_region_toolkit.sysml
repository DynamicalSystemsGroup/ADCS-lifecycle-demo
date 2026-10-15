package LinearADCS {
    private import ScalarValues::*;
    // Linear per-axis model J s^2 + Kd s + Kp/4 (analysis/symbolic.py). Settling 4/|Re s| <= 120 s
    // is equivalent to Re s <= -sigma, sigma = 1/30, i.e. both shifted coefficients non-negative.
    constraint def AxisSettles {
        in J : Rational[1]; in Kp : Rational[1]; in Kd : Rational[1];
        Kd >= 2 * J / 30 and Kp / 4 >= Kd / 30 - J / 900
    }
    constraint def LinearSettles {
        in Kp : Rational[1]; in Kd : Rational[1];
        Kp > 0 and Kd > 0
        and Kd >= 2 * 327.1367 / 30 and Kp / 4 >= Kd / 30 - 327.1367 / 900
        and Kd >= 2 * 107.4783 / 30 and Kp / 4 >= Kd / 30 - 107.4783 / 900
        and Kd >= 2 * 303.4483 / 30 and Kp / 4 >= Kd / 30 - 303.4483 / 900
    }
    // No actuator saturation at the 10 degree slew start: (Kp/2) * sin(5 deg) <= 0.1 N m
    constraint def Unsaturated {
        in Kp : Rational[1];
        Kp * 0.0871557 / 2 <= 0.1
    }
    constraint def RegionPasses {
        in Kp : Rational[1]; in Kd : Rational[1];
        (Kp >= 4 and Kp <= 6 and Kd >= 22 and Kd <= 25) implies (Kp > 0 and Kd > 0
        and Kd >= 2 * 327.1367 / 30 and Kp / 4 >= Kd / 30 - 327.1367 / 900
        and Kd >= 2 * 107.4783 / 30 and Kp / 4 >= Kd / 30 - 107.4783 / 900
        and Kd >= 2 * 303.4483 / 30 and Kp / 4 >= Kd / 30 - 303.4483 / 900)
    }
    constraint def ValidAndSettles {
        in Kp : Rational[1]; in Kd : Rational[1];
        (Kp > 0 and Kd > 0
        and Kd >= 2 * 327.1367 / 30 and Kp / 4 >= Kd / 30 - 327.1367 / 900
        and Kd >= 2 * 107.4783 / 30 and Kp / 4 >= Kd / 30 - 107.4783 / 900
        and Kd >= 2 * 303.4483 / 30 and Kp / 4 >= Kd / 30 - 303.4483 / 900) and Kp * 871557 <= 2000000
    }
}
