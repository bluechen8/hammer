// Functional simulation models for the sky130_fd_io pad primitives.
//
// WHY THESE EXIST
// ---------------
// The PDK's behavioral models implement timing-check violations by corrupting
// their own outputs to X, via a notifier register driven by $setuphold:
//
//     reg  notifier_enable_h;                          // $setuphold notifier
//     always @(notifier_enable_h) corrupt_enable <= 1'bx;
//     initial                     corrupt_enable  = 1'b0;
//     always @(PAD or ENABLE_H or ...) corrupt_enable <= 1'b0;  // cleared only on the
//                                                              // NEXT input transition
//     wire xres_tmp = (... || corrupt_enable===1'bx || ...) ? 1'bx : PAD;
//
// The Chipyard sim flow compiles with +notimingcheck -- it has already opted out
// of timing-violation X injection -- but it also passes +vcs+initreg, which
// initialises EVERY reg in the design at time 0, notifier_enable_h included.
// That write is a value change, so `always @(notifier_enable_h)` fires and
// latches corrupt_enable = 1'bx even though no timing check ran. Nothing clears
// it until the pad's next input transition, which for the reset pad is porb_h
// rising at the end of the 500ns simple_por ramp.
//
// Net effect on a real design: the chip's reset is X for the first 500ns while
// the clock is already free-running, so ~500 clock edges land with reset = X.
// The X settles into flops that have no reset connection and then circulates
// forever -- holding reset valid for a further 3us afterwards does NOT recover
// it (measured). The design never boots and gate-level sim times out.
//
// VCS cannot scope +vcs+initreg (this VCS documents only
// "+vcs+initreg+0|1|x|z  Initializes all bits of all regs in the design"), and
// dropping +vcs+initreg is not an option: force_regs.ucli does not cover every
// piece of gate-level state, so the netlist then starts under-initialised.
//
// So the pads are modeled functionally instead. This is the same call already
// made for sky130_ef_io.v and simple_por.v in this directory: simulation-only,
// never reaches synthesis, P&R, DRC or LVS.
//
// WHAT THIS GIVES UP
// ------------------
// These models implement the digital signal path only. They deliberately do NOT
// model: hold mode (HLD_H_N / HLD_OVR), input disable (INP_DIS), pull-ups
// (DISABLE_PULLUP_H / PULLUP_H), input trip point (VTRIP_SEL), slew (SLOW),
// input buffer mode (IB_MODE_SEL), the analog mux (ANALOG_EN / ANALOG_SEL /
// ANALOG_POL / AMUXBUS_*), or power-up sequencing on the supply pins.
//
// Gate-level sim therefore no longer validates IO *configuration* -- if a config
// pin were mis-tied, these models would do the right thing while silicon did not.
// In the Chipyard flow those pins are tied to constants in the netlist, so check
// them once structurally rather than relying on simulation to catch it.
//
// For power and IR-drop this loses nothing: Voltus/Joules derive IO-cell power
// from the library model driven by pin-level toggle activity, not from the sim
// model's internal nodes, and these models preserve pin-level behaviour. The
// pads also sit on VDDIO/VDDA rather than the core VCCD rail.
//
// Only the primitives Chipyard instantiates are modeled here; add more as needed.

`timescale 1ns/1ps

// ---------------------------------------------------------------------------
// Reset pad. XRES_H_N follows PAD (or FILT_IN_H when INP_SEL_H selects it).
// ---------------------------------------------------------------------------
module sky130_fd_io__top_xres4v2 ( TIE_WEAK_HI_H, XRES_H_N, TIE_HI_ESD, TIE_LO_ESD,
                                   AMUXBUS_A, AMUXBUS_B, PAD, PAD_A_ESD_H, ENABLE_H,
                                   EN_VDDIO_SIG_H, INP_SEL_H, FILT_IN_H,
                                   DISABLE_PULLUP_H, PULLUP_H, ENABLE_VDDIO
                                 );
  output XRES_H_N;
  inout  AMUXBUS_A, AMUXBUS_B;
  inout  PAD, PAD_A_ESD_H;
  input  DISABLE_PULLUP_H, ENABLE_H, EN_VDDIO_SIG_H, INP_SEL_H, FILT_IN_H;
  inout  PULLUP_H;
  input  ENABLE_VDDIO;
  output TIE_HI_ESD, TIE_LO_ESD;
  inout  TIE_WEAK_HI_H;

  // ESD/pad tie-throughs, as in the PDK model.
  //
  // TIE_WEAK_HI_H must be a *weak* pull, not a strong drive. Sky130FDXRes4V2IOCell
  // wires PAD_A_ESD_H and TIE_WEAK_HI_H to the same net, and `tran p2` ties that net
  // to PAD -- so driving TIE_WEAK_HI_H with a strong `assign 1'b1` puts a second
  // strong driver on the pad and the reset input resolves to X whenever the
  // testbench drives 0. The PDK model uses `pullup (pull1)` for exactly this reason;
  // pull1 loses to the strong driver instead of fighting it.
  tran p2 (PAD, PAD_A_ESD_H);
  pullup (pull1) pu_weak_hi (TIE_WEAK_HI_H);
  assign TIE_HI_ESD    = 1'b1;
  assign TIE_LO_ESD    = 1'b0;

  // Signal path. ENABLE_H gates the pad in silicon during power-up; the chip is
  // held in reset then, so the simulation value that matters is the pad input.
  assign XRES_H_N = (INP_SEL_H === 1'b1) ? FILT_IN_H : PAD;
endmodule

// ---------------------------------------------------------------------------
// GPIO pad. Bidirectional: OE_N low drives OUT onto PAD, IN/IN_H follow PAD.
// Instantiated by sky130_ef_io__gpiov2_pad_wrapped in sky130_ef_io.v.
// ---------------------------------------------------------------------------
module sky130_fd_io__top_gpiov2 (IN_H, PAD_A_NOESD_H, PAD_A_ESD_0_H, PAD_A_ESD_1_H,
                                 PAD, DM, HLD_H_N, IN, INP_DIS, IB_MODE_SEL, ENABLE_H,
                                 ENABLE_VDDA_H, ENABLE_INP_H, OE_N, TIE_HI_ESD,
                                 TIE_LO_ESD, SLOW, VTRIP_SEL, HLD_OVR, ANALOG_EN,
                                 ANALOG_SEL, ENABLE_VDDIO, ENABLE_VSWITCH_H,
                                 ANALOG_POL, OUT, AMUXBUS_A, AMUXBUS_B
                                );
  input  OUT, OE_N, HLD_H_N, ENABLE_H, ENABLE_INP_H, ENABLE_VDDA_H;
  input  ENABLE_VSWITCH_H, ENABLE_VDDIO, INP_DIS, IB_MODE_SEL, VTRIP_SEL;
  input  SLOW, HLD_OVR, ANALOG_EN, ANALOG_SEL, ANALOG_POL;
  input  [2:0] DM;
  inout  PAD, PAD_A_NOESD_H, PAD_A_ESD_0_H, PAD_A_ESD_1_H;
  inout  AMUXBUS_A, AMUXBUS_B;
  output IN, IN_H;
  output TIE_HI_ESD, TIE_LO_ESD;

  tran p0 (PAD, PAD_A_NOESD_H);
  tran p1 (PAD, PAD_A_ESD_0_H);
  tran p2 (PAD, PAD_A_ESD_1_H);
  assign TIE_HI_ESD = 1'b1;
  assign TIE_LO_ESD = 1'b0;

  // Output driver: enabled when OE_N is low.
  assign PAD = (OE_N === 1'b0) ? OUT : 1'bz;

  // Input buffers. INP_DIS squelches the low-voltage input in silicon; modeled
  // so a disabled input reads 0 rather than X.
  assign IN   = (INP_DIS === 1'b1) ? 1'b0 : PAD;
  assign IN_H = PAD;
endmodule
