package LinearADCS {
    private import ScalarValues::*;
    // Template: sysml/formal.py fills the upper-case tokens between at-signs at run time: inertias JXX JYY JZZ
    // (analysis.symbolic.evaluate_inertia), the box KP_LO..KD_HI, SIN5 (sin of half the slew angle) and TAUMAX.
    // Linear per-axis model J s^2 + Kd s + Kp/4 (analysis/symbolic.py). Settling 4/|Re s| <= 120 s
    // is equivalent to Re s <= -sigma, sigma = 1/30, i.e. both shifted coefficients non-negative.
    constraint def LinearSettles {
        in Kp : Rational; in Kd : Rational;
        Kp > 0 and Kd > 0
        and Kd >= 2 * @JXX@ / 30 and Kp / 4 >= Kd / 30 - @JXX@ / 900
        and Kd >= 2 * @JYY@ / 30 and Kp / 4 >= Kd / 30 - @JYY@ / 900
        and Kd >= 2 * @JZZ@ / 30 and Kp / 4 >= Kd / 30 - @JZZ@ / 900
    }
    // Every point of the box satisfies the linear settling condition.
    constraint def RegionSettles {
        in Kp : Rational; in Kd : Rational;
        (Kp >= @KP_LO@ and Kp <= @KP_HI@ and Kd >= @KD_LO@ and Kd <= @KD_HI@) implies (Kp > 0 and Kd > 0
        and Kd >= 2 * @JXX@ / 30 and Kp / 4 >= Kd / 30 - @JXX@ / 900
        and Kd >= 2 * @JYY@ / 30 and Kp / 4 >= Kd / 30 - @JYY@ / 900
        and Kd >= 2 * @JZZ@ / 30 and Kp / 4 >= Kd / 30 - @JZZ@ / 900)
    }
    // Linear settling AND no actuator saturation at the slew start: (Kp/2) sin(5 deg) <= tauMax
    constraint def ValidAndSettles {
        in Kp : Rational; in Kd : Rational;
        (Kp > 0 and Kd > 0
        and Kd >= 2 * @JXX@ / 30 and Kp / 4 >= Kd / 30 - @JXX@ / 900
        and Kd >= 2 * @JYY@ / 30 and Kp / 4 >= Kd / 30 - @JYY@ / 900
        and Kd >= 2 * @JZZ@ / 30 and Kp / 4 >= Kd / 30 - @JZZ@ / 900)
        and Kp * @SIN5@ / 2 <= @TAUMAX@
    }
}
