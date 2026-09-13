// Simulation models for the sky130_ef_io pad wrappers.
//
// The PDK's own sky130A/libs.ref/sky130_fd_io/verilog/sky130_ef_io.v cannot be
// compiled for simulation: its wrappers unconditionally declare the pad supply
// pins as ports and pass them down to sky130_fd_io__top_gpiov2, which only
// declares those ports under `USE_POWER_PINS`. Defining USE_POWER_PINS is not a
// fix either -- nothing in a Chipyard netlist connects pad supplies, so the
// behavioral model would see floating supplies and drive X onto every pad.
//
// The ef_io wrappers are pure pass-throughs (they exist to re-route the power
// bus in layout, not to change behavior), so these models declare the same
// ports and connect only the signal pins. sky130_fd_io__top_gpiov2 then uses
// its own internal `supply1`/`supply0` nets for the rails, which is what makes
// the pad functional in simulation.
//
// Only the wrappers Chipyard instantiates are modeled here; add more as needed.

`timescale 1ns/1ps

module sky130_ef_io__gpiov2_pad_wrapped (IN_H, PAD_A_NOESD_H, PAD_A_ESD_0_H, PAD_A_ESD_1_H,
    PAD, DM, HLD_H_N, IN, INP_DIS, IB_MODE_SEL, ENABLE_H, ENABLE_VDDA_H,
    ENABLE_INP_H, OE_N, TIE_HI_ESD, TIE_LO_ESD, SLOW, VTRIP_SEL, HLD_OVR,
    ANALOG_EN, ANALOG_SEL, ENABLE_VDDIO, ENABLE_VSWITCH_H, ANALOG_POL, OUT,
    AMUXBUS_A, AMUXBUS_B, VSSA, VDDA, VSWITCH, VDDIO_Q, VCCHIB, VDDIO, VCCD,
    VSSIO, VSSD, VSSIO_Q
    );

input OUT;
input OE_N;
input HLD_H_N;
input ENABLE_H;
input ENABLE_INP_H;
input ENABLE_VDDA_H;
input ENABLE_VSWITCH_H;
input ENABLE_VDDIO;
input INP_DIS;
input IB_MODE_SEL;
input VTRIP_SEL;
input SLOW;
input HLD_OVR;
input ANALOG_EN;
input ANALOG_SEL;
input ANALOG_POL;
input [2:0] DM;

// Declared to match the macro's port list, deliberately left unconnected below.
inout VDDIO;
inout VDDIO_Q;
inout VDDA;
inout VCCD;
inout VSWITCH;
inout VCCHIB;
inout VSSA;
inout VSSD;
inout VSSIO_Q;
inout VSSIO;

inout PAD;
inout PAD_A_NOESD_H, PAD_A_ESD_0_H, PAD_A_ESD_1_H;
inout AMUXBUS_A;
inout AMUXBUS_B;

output IN;
output IN_H;
output TIE_HI_ESD, TIE_LO_ESD;

sky130_fd_io__top_gpiov2 gpiov2_base (
    .IN_H(IN_H),
    .PAD_A_NOESD_H(PAD_A_NOESD_H),
    .PAD_A_ESD_0_H(PAD_A_ESD_0_H),
    .PAD_A_ESD_1_H(PAD_A_ESD_1_H),
    .PAD(PAD),
    .DM(DM),
    .HLD_H_N(HLD_H_N),
    .IN(IN),
    .INP_DIS(INP_DIS),
    .IB_MODE_SEL(IB_MODE_SEL),
    .ENABLE_H(ENABLE_H),
    .ENABLE_VDDA_H(ENABLE_VDDA_H),
    .ENABLE_INP_H(ENABLE_INP_H),
    .OE_N(OE_N),
    .TIE_HI_ESD(TIE_HI_ESD),
    .TIE_LO_ESD(TIE_LO_ESD),
    .SLOW(SLOW),
    .VTRIP_SEL(VTRIP_SEL),
    .HLD_OVR(HLD_OVR),
    .ANALOG_EN(ANALOG_EN),
    .ANALOG_SEL(ANALOG_SEL),
    .ENABLE_VDDIO(ENABLE_VDDIO),
    .ENABLE_VSWITCH_H(ENABLE_VSWITCH_H),
    .ANALOG_POL(ANALOG_POL),
    .OUT(OUT),
    .AMUXBUS_A(AMUXBUS_A),
    .AMUXBUS_B(AMUXBUS_B)
);

endmodule
