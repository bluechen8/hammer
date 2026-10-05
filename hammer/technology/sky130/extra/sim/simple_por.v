// Simulation model for the Caravel simple_por macro.
//
// The PDK's own behavioral model, caravel/verilog/rtl/simple_por.v, ramps its
// internal node off the vdd3v3 supply pin. That pin only exists under
// `USE_POWER_PINS`, so without the define the file does not compile (vdd3v3 is
// referenced but never declared, under `default_nettype none`), and with the
// define the supply pins are left unconnected by both the Chipyard RTL and the
// synthesized netlist -- porb_h would never rise and the design would never
// leave reset.
//
// This model exposes exactly the three signal ports ChipTop connects and
// reproduces the PDK model's polarity and 500ns POR ramp, so RTL and
// gate-level simulations see a real power-on-reset pulse. It is wired in via
// the `por` library's verilog_sim in example-designs/caliptra-rocket-sky130.yml.

`timescale 1ns/1ps

module simple_por (
    output porb_h,
    output porb_l,
    output por_l
);

  // The real macro dumps current onto a capacitor over ~15ms; the PDK
  // behavioral model speeds that up to 500ns. Match the model, which keeps the
  // pulse inside TestDriver's RESET_DELAY.
  reg porb = 1'b0;

  initial begin
    porb = 1'b0;
    #500 porb = 1'b1;
  end

  assign porb_h = porb;
  assign porb_l = porb;
  assign por_l  = ~porb;

endmodule
