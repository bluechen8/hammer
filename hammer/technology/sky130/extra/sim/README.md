# sky130 simulation models

Behavioral models that RTL and gate-level simulation need, but that the PDK either
does not ship or ships in a form that cannot be compiled. Everything here is
simulation-only — none of it reaches synthesis, P&R, DRC or LVS.

Both models are wired up from `../../__init__.py`, not from user YAML, so they
apply to every flow step automatically — including `redo-` steps replaying an
older config snapshot.

## What is here

| File | Replaces | Wired in by |
|---|---|---|
| `simple_por.v` | `${technology.sky130.caravel}/verilog/rtl/simple_por.v` | `SKY130Tech.get_extra_libraries` |
| `sky130_ef_io.v` | `${technology.sky130.sky130A}/.../sky130_ef_io.v` | `SKY130Tech.gen_config`, per-library redirect |
| `sky130_fd_io.v` | `${technology.sky130.sky130A}/.../sky130_fd_io.v` | `SKY130Tech.gen_config`, per-library redirect |

## Why the pad primitives are modeled and not used as shipped

The PDK's `sky130_fd_io` models corrupt their own outputs to X on a timing-check
violation, via a notifier reg driven by `$setuphold`. The flow sets `+notimingcheck`,
so no check ever fires -- but it also sets `+vcs+initreg`, which writes *every* reg at
time 0, notifiers included. That write is a value change, so the corruption fires
anyway and is not cleared until the pad's next input transition. On the reset pad that
is `porb_h` rising 500ns later, so the chip's reset is X for 500ns of free-running
clock, which poisons every flop that has no reset. `+vcs+initreg` cannot be scoped, and
dropping it leaves the netlist under-initialised instead, so the pads are modeled.

The `sky130_fd_sc_hvl` level shifter is deliberately not modeled -- it was measured
propagating correctly, and it is declared from user YAML, not from this plugin.

These models cover the digital signal path only; each file's header lists what is
left out (hold mode, input disable, pull-ups, trip point, slew, analog mux). Gate-level
sim therefore does not validate IO *configuration* -- check those tied pins
structurally.

## Cadence `sky130_scl_9T` standard cells: used verbatim, no model needed

`${technology.sky130.sky130_scl}/sky130_scl_9T/verilog/sky130_scl_9T.v` (Liberate
20.1.0, 109 cells) is used **as shipped** — no edits, no supplements. Its cells are
plain structural primitives over Cadence `altos_*` UDPs with every `specify` path at
`= 0`, so it is already a correct zero-delay model and compiles clean under VCS.

It deliberately covers only the cells with a `.lib` timing entry. The physical-only
cells in `sky130_scl_9T_tech/lef/sky130_scl_9T_phyCells.lef` have no function and no
Verilog, **and that is expected** — they are meant to be *stripped from the netlist*,
not modeled.

Hammer already does this: `write_netlist` is called with
`-exclude_insts_of_cells { <physical_only_cells> }`. The bug was that the sky130
plugin only populated `physical_only_cells_list` for the `sky130_fd_sc_hd` standard
cell library; for `sky130_scl` it was left empty, so the exclusion list came out blank
and Innovus-inserted `ANTENNA` diodes survived into `ChipTop.sim.v` (13,167 of them —
they get past `-exclude_leaf_cells` because they have a signal pin). Gate-level sim
then died with `Error-[CFCILFBI] Cannot find cell in liblist`.

The fix is in the Hammer patch: declare the ten physical-only cells for `sky130_scl`.

```
ANTENNA  FILL1 FILL2 FILL4 FILL8 FILL16 FILL32 FILL64  FILL_DECAP8 FILL_DECAP16
```

`TIEHI`/`TIELO` are deliberately **not** in that list — they drive real values, are
modeled in the Cadence file, and stripping them would leave nets undriven.

To restrip an existing P&R result without re-running `par`, restore the Innovus
database and rewrite just the sim netlist (about 3 minutes):

```tcl
read_db <par-rundir>/ChipTop_FINAL
write_netlist <par-rundir>/ChipTop.sim.v -top_module_first -top_module ChipTop \
  -exclude_leaf_cells \
  -exclude_insts_of_cells { ANTENNA FILL1 FILL2 FILL4 FILL8 FILL16 FILL32 FILL64 FILL_DECAP8 FILL_DECAP16 }
```

The pre-strip netlist for the current build is kept as `ChipTop.sim.v.unstripped`.

## `simple_por.v` — Caravel POR macro

The PDK's behavioral model ramps its internal node off the `vdd3v3` supply pin.
That pin only exists under `USE_POWER_PINS`, which leaves two dead ends:

- Without the define the file does not compile at all: `vdd3v3` is referenced in
  the `always` blocks but never declared, under `` `default_nettype none ``.
- With the define, nothing in either the Chipyard RTL or the synthesized netlist
  connects the pad supplies, so `vdd3v3` floats, `porb_h` never rises, and the
  design never leaves power-on reset.

Our model exposes exactly the three signal ports `ChipTop` connects and reproduces
the PDK model's polarity and 500 ns POR ramp.

## `sky130_ef_io.v` — IO pad wrappers

The PDK's `sky130_ef_io.v` has the same shape of problem as the POR macro: its
wrappers unconditionally declare the pad supply pins as ports and pass them down to
`sky130_fd_io__top_gpiov2`, which only declares those ports under `USE_POWER_PINS`.
VCS rejects it with `Error-[UPIMI-E] Undefined port in module instantiation`, and
defining `USE_POWER_PINS` would just move the failure — the supplies are unconnected,
so the pad would drive X.

The ef_io wrappers are pure pass-throughs (they exist to re-route the power bus in
layout, not to change behavior), so our model declares the same ports and connects
only the signal pins. `sky130_fd_io__top_gpiov2` then falls back on its own internal
`supply1`/`supply0` nets for the rails, which is what makes the pad functional in
simulation.

Only `sky130_ef_io__gpiov2_pad_wrapped` is modeled — the one wrapper this design
instantiates. Add more the same way if a design needs them.

## Plugin changes that go with these models

All in `../../__init__.py`:

1. **Fix the `verilog_sim` paths.** The plugin built every library's gate-level
   Verilog path as `${sky130_scl}/sky130_scl_9T/verilog/<library>_9T.v`. For the
   standard cells that resolves to `sky130_scl_9T_9T.v`, and for the IO libraries
   to `sky130_fd_io_9T.v` / `sky130_ef_io_9T.v` — none of which exist. Hammer's
   `read_libs` existence check then raised `ValueError` before VCS was ever
   invoked, so *every* simulation failed, RTL included. Models now resolve next to
   their own library, and `verilog_sim` is left unset when the PDK has no model.

2. **Redirect `sky130_ef_io`** at the sim model described above, and override
   `get_extra_libraries` to redirect a Caravel `simple_por` the same way.

3. **Declare `physical_only_cells_list` for `sky130_scl`**, so `write_netlist`
   strips the fill/decap/antenna cells instead of needing Verilog for them.
