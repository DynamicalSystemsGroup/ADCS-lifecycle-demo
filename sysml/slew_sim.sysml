package SlewSim {
    private import ScalarValues::*;
    // Template: sysml/evidence.py (inmodel_settling) fills the upper-case tokens between at-signs.
    // Single-axis PD slew with actuator saturation, explicit Euler steps of dt, executed by the
    // OpenSysML action interpreter. tau = -(Kp/2) * (theta/2) - Kd * omega, clipped to +/- tauMax
    // (analysis/numerical.py with the small-angle error, theta/2 = quaternion vector part).
    // Settling = last time |theta| exceeds 1% of the initial 10 degree error.
    action def Slew {
        attribute J : Real = @J@;
        attribute Kp : Real = @KP@;
        attribute Kd : Real = @KD@;
        attribute tauMax : Real = @TAUMAX@;
        attribute dt : Real = @DT@;
        out tSettle : Real;
        attribute theta : Real := @THETA0@;
        attribute omega : Real := 0.0;
        attribute t : Real := 0.0;
        attribute tau : Real := 0.0;
        attribute lastOut : Real := 0.0;
        while t < @TEND@ {
            assign tau := -(Kp / 2) * (theta / 2) - Kd * omega;
            if tau > tauMax { assign tau := tauMax; }
            if tau < -tauMax { assign tau := -tauMax; }
            assign omega := omega + dt * tau / J;
            assign theta := theta + dt * omega;
            assign t := t + dt;
            if theta > @BAND@ or theta < -@BAND@ { assign lastOut := t; }
        }
        then assign tSettle := lastOut;
    }
    action slew : Slew;
}
