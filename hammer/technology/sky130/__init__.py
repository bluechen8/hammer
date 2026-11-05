#  SKY130 plugin for Hammer.
#
#  See LICENSE for licence details.

import functools
import importlib
import importlib.resources
import json
import os
import re
import shutil
from pathlib import Path
from typing import List

from hammer.tech import (
    filters,
    Corner,
    Decimal,
    DRCDeck,
    ExtraLibrary,
    HammerTechnology,
    HammerTechnologyUtils,
    Library,
    LVSDeck,
    Metal,
    PathPrefix,
    Provide,
    Site,
    SpiceModelFile,
    Stackup,
    Supplies,
    TechJSON,
)
from hammer.tech.specialcells import CellType, SpecialCell
from hammer.utils import LEFUtils
from hammer.vlsi import (
    HammerDRCTool,
    HammerLVSTool,
    HammerPlaceAndRouteTool,
    HammerTool,
    HammerToolHookAction,
    HierarchicalMode,
    TCLTool,
)

from hammer.tech.specialcells import CellType, SpecialCell

from hammer.utils import LEFUtils
from hammer.vlsi import (
    HammerDRCTool,
    HammerLVSTool,
    HammerPlaceAndRouteTool,
    HammerTool,
    HammerToolHookAction,
    HierarchicalMode,
    TCLTool,
)

class SKY130Tech(HammerTechnology):
    """
    Override the HammerTechnology used in `hammer_tech.py`
    This class is loaded by function `load_from_json`, and will pass the `try` in `importlib`.
    """
    
    def gen_config(self) -> None:
        """Generate the tech config, based on the library type selected"""
        
        slib = self.get_setting("technology.sky130.stdcell_library")
        SKY130A = self.get_setting("technology.sky130.sky130A")
        SKY130_CDS = self.get_setting("technology.sky130.sky130_cds")
        SKY130_SCL = self.get_setting("technology.sky130.sky130_scl")
        SRAM22 = self.get_setting("technology.sky130.sram22_sky130_macros")
        
        # SKY130_IO = self.get_setting("technology.sky130.io_periphery_cells") # TODO(jimfang) make it so that users dont need to install entire openPDKs just for the IO cells... thisi may mean republishing the IO cells (after the installer's ef_io io cells modification) at a github location... for now, we depend on SKY130A (open pdks) even for the CDNS std cell flow...
        
        # Common tech LEF and IO cell spice netlists
        libs = []
        if slib == "sky130_fd_sc_hd":
            libs += [
                Library(
                    lef_file=os.path.join(
                        SKY130A,
                        "libs.ref/sky130_fd_sc_hd/techlef/sky130_fd_sc_hd__nom.tlef",
                    ),
                    verilog_sim=os.path.join(
                        SKY130A, "libs.ref/sky130_fd_sc_hd/verilog/primitives.v"
                    ),
                    provides=[Provide(lib_type="technology")],
                ),
            ]
        elif slib == "sky130_scl":
            libs += [
                Library(
                    lef_file="cache/sky130_scl_9T.tlef",
                    verilog_sim=os.path.join(SKY130_SCL, "sky130_scl_9T/verilog/sky130_scl_9T.v"),
                    provides=[Provide(lib_type="technology")],
                ),
            ]
            libs += [
                Library(
                    lef_file=os.path.join(SKY130_SCL, "sky130_scl_9T_tech/lef/sky130_scl_9T_phyCells.lef"),
                    gds_file=os.path.join(SKY130_SCL, "sky130_scl_9T_tech/gds/sky130_scl_9T_tech.gds"),
                    provides=[Provide(lib_type="technology")],
                ),
            ]
        else:
            raise ValueError(f"Incorrect standard cell library selection: {slib}")
        
        
        # Use SRAM22
        libs += [
                Library(
                    spice_file=os.path.join(
                        SRAM22,
                        "sram22.spice",
                    ),
                    provides=[Provide(lib_type="technology")],
                ),
        ]
        
        # Stdcell library-dependent lists
        stackups = []  # type: List[Stackup]
        phys_only = []  # type: List[Cell]
        dont_use = []  # type: List[Cell]
        spcl_cells = []  # type: List[SpecialCell]
        
        # base path -> list of corners
        lib_corner_files = {}
        
        if slib == "sky130_fd_sc_hd":
            phys_only = [
                "sky130_fd_sc_hd__fill_1",
                "sky130_fd_sc_hd__fill_2",
                "sky130_fd_sc_hd__fill_4",
                "sky130_fd_sc_hd__fill_8",
                "sky130_fd_sc_hd__decap_3",
                "sky130_fd_sc_hd__decap_4",
                "sky130_fd_sc_hd__decap_6",
                "sky130_fd_sc_hd__decap_8",
                "sky130_fd_sc_hd__decap_12",
                "sky130_fd_sc_hd__tap_1",
                "sky130_fd_sc_hd__tap_2",
                "sky130_fd_sc_hd__tapvgnd_1",
                "sky130_fd_sc_hd__tapvpwrvgnd_1",
                "sky130_fd_sc_hd__diode_2",
            ]
            
            dont_use = [
                "*sdf*",
                "sky130_fd_sc_hd__probe_p_*",
                "sky130_fd_sc_hd__probec_p_*",
            ]
            
            spcl_cells = [
                # for now, skipping the tiecell step. I think the extracted verilog netlist is ignoring the tiecells which is causing lvs issues
                # TODO(jimfang) is this during extraction of verilog after par? or something done here/hacked up here? sometimes lvs doesn't fully include phycells.. is this is misconfig of some kind?
                SpecialCell(
                    cell_type=CellType("tiehilocell"), name=["sky130_fd_sc_hd__conb_1"]
                ),
                SpecialCell(
                    cell_type=CellType("tiehicell"),
                    name=["sky130_fd_sc_hd__conb_1"],
                    output_ports=["HI"],
                ),
                SpecialCell(
                    cell_type=CellType("tielocell"),
                    name=["sky130_fd_sc_hd__conb_1"],
                    output_ports=["LO"],
                ),
                SpecialCell(
                    cell_type=CellType("endcap"), name=["sky130_fd_sc_hd__tap_1"]
                ),
                SpecialCell(
                    cell_type=CellType("tapcell"),
                    name=["sky130_fd_sc_hd__tapvgnd_1", "sky130_fd_sc_hd__tapvpwrvgnd_1"],
                ),
                SpecialCell(
                    # sky130_ef_sc_hd__fill_4 etc also exist; we don't use them; this is intentional.
                    # If you are running into LI density (too much) errors, consider using the sky130_ef_sc_hd__ cells
                    # see: https://github.com/fossi-foundation/open-pdks/tree/main/sky130/custom/sky130_fd_sc_hd#readme
                    cell_type=CellType("stdfiller"),
                    name=[
                        "sky130_fd_sc_hd__fill_1",
                        "sky130_fd_sc_hd__fill_2",
                        "sky130_fd_sc_hd__fill_4",
                        "sky130_fd_sc_hd__fill_8",
                    ],
                ),
                SpecialCell(
                    cell_type=CellType("decap"),
                    name=[
                        "sky130_fd_sc_hd__decap_3",
                        "sky130_fd_sc_hd__decap_4",
                        "sky130_fd_sc_hd__decap_6",
                        "sky130_fd_sc_hd__decap_8",
                        "sky130_fd_sc_hd__decap_12",
                    ],
                ),
                SpecialCell(
                    cell_type=CellType("driver"),
                    name=["sky130_fd_sc_hd__buf_4"],
                    input_ports=["A"],
                    output_ports=["X"],
                ),
                # this breaks synthesis with a complaint about "Cannot perform synthesis because libraries do not have usable inverters." from Genus.
                # note that innovus still recognizes and uses this cell as a buffer
                # TODO(jimfang) https://github.com/ucb-bar/hammer/blob/516aedb55385e9e3d9237738db5c8c2978e6475c/hammer/synthesis/genus/__init__.py#L337 - wrong tcl call for newer innovus versions?
                SpecialCell(
                    cell_type=CellType("ctsbuffer"), name=["sky130_fd_sc_hd__clkbuf_1"]
                ),
                
                # TODO(jimfang) below newly added
                SpecialCell(
                    cell_type=CellType("ctsinverter"),
                    name=[
                        "sky130_fd_sc_hd__clkinv_1",
                        "sky130_fd_sc_hd__clkinv_2",
                        "sky130_fd_sc_hd__clkinv_4",
                        "sky130_fd_sc_hd__clkinv_8",
                        "sky130_fd_sc_hd__clkinv_16"
                    ]
                ),
                
                SpecialCell(
                    cell_type=CellType("ctsgate"),
                    name=[
                        "sky130_fd_sc_hd__dlclkp_1",
                        "sky130_fd_sc_hd__dlclkp_2",
                        "sky130_fd_sc_hd__dlclkp_4"
                    ]
                )
            ]

            # Generate standard cell library
            library = slib
            
            # TODO(jimfang) - i dont think this is needed?
            # # scl vs 130a have different site names
            # sites = None
            
            # grab corners
            STDCELL_LIBRARY_BASE_PATH = os.path.join(SKY130A, "libs.ref", library)
            lib_corner_files[STDCELL_LIBRARY_BASE_PATH] = os.listdir(
                os.path.join(STDCELL_LIBRARY_BASE_PATH, "lib")
            )
            lib_corner_files[STDCELL_LIBRARY_BASE_PATH].sort()
            
            
            tlef_path = os.path.join(
                SKY130A, "libs.ref", library, "techlef", f"{library}__min.tlef"
            )
            metals = list(
                map(lambda m: Metal.model_validate(m), LEFUtils.get_metals(tlef_path))
            )
            stackups.append(
                Stackup(name=slib, grid_unit=Decimal("0.001"), metals=metals)
            )

            sites = [
                Site(name="unithd", x=Decimal("0.46"), y=Decimal("2.72")),
                Site(name="unithddbl", x=Decimal("0.46"), y=Decimal("5.44")),
            ]
            lvs_decks = [
                # sky130A uses NDA-ed or Cadence LVS decks as Hammer doesn't have klayout LVS support as of July 2026
                LVSDeck(
                    tool_name="calibre",
                    deck_name="calibre_lvs",
                    path="$SKY130_NDA/s8/V2.0.1/LVS/Calibre/lvsRules_s8",
                ),
                LVSDeck(
                    tool_name="pegasus",
                    deck_name="pegasus_lvs",
                    path=self.get_setting("technology.sky130.lvs_deck"),
                ),
            ]
            drc_decks = [
                DRCDeck(
                    tool_name="calibre",
                    deck_name="calibre_drc",
                    path="$SKY130_NDA/s8/V2.0.1/DRC/Calibre/s8_drcRules",
                ),
                DRCDeck(
                    tool_name="klayout",
                    deck_name="klayout_drc",
                    path="$SKY130A/libs.tech/klayout/drc/sky130A.lydrc",
                ),
                DRCDeck(
                    tool_name="pegasus",
                    deck_name="pegasus_drc",
                    path=self.get_setting("technology.sky130.drc_deck"),
                ),
            ]
        
        elif slib == "sky130_scl":
            # cadence standard cells & PDK do not provide IO cells; we'll use IO cells provided here: https://github.com/fossi-foundation/open-pdks/tree/main/sky130 -- see notes at line `if "sky130_fd_io" in library_base_path:`
            
            phys_only = [
                "FILL1",
                "FILL2",
                "FILL4",
                "FILL8",
                "FILL16",
                "FILL32",
                "FILL64",
                "FILL_DECAP8",
                "FILL_DECAP16",
                "ANTENNA"              
            ]
            
            dont_use = [
                
            ]
            
            spcl_cells = [
                SpecialCell(
                    cell_type=CellType("tiehicell"), name=["TIEHI"], input_ports=["Y"]
                ),
                SpecialCell(
                    cell_type=CellType("tielocell"), name=["TIELO"], input_ports=["Y"]
                ),
                # cadence sky130 std cells don't have a endcap TODO(jimfang) is this intended?
                # cadnece sky130 std cells contain taps by default (not a tapless design unlike the sky130A cells)
                
                # TODO(jimfang) below newly added
                SpecialCell(
                    cell_type=CellType("stdfiller"),
                    name=[
                        "FILL1",
                        "FILL2",
                        "FILL4",
                        "FILL8",
                        "FILL16",
                        "FILL32",
                        "FILL64",
                    ],
                ),
                
                SpecialCell(
                    cell_type=CellType("decap"),
                    name=[
                        "FILL_DECAP8",
                        "FILL_DECAP16",
                    ],
                ),
                
                SpecialCell(
                    cell_type=CellType("driver"),
                    name=[
                        "BUFX2",
                        "BUFX4",
                        "BUFX8",
                        "BUFX16",
                    ],
                ),
                
                SpecialCell(
                    cell_type=CellType("ctsbuffer"), name=[
                        "CLKBUFX2",
                        "CLKBUFX4",
                        "CLKBUFX8"
                    ]
                ),
                
                SpecialCell(
                    cell_type=CellType("ctsinverter"), name=[
                        "CLKINVX1",
                        "CLKINVX2",
                        "CLKINVX4",
                        "CLKINVX8",
                    ]
                ),
                
                SpecialCell(
                    cell_type=CellType("ctsgate"), name=[
                        "ICGX1"
                    ]
                ),
                
            ]
            
            
            # Generate standard cell library
            library = slib
            
            # grab corners
            # TODO(jimfang) can this process a lib.gz directly or do we need to unzip it when installing the PDK?
            STDCELL_LIBRARY_BASE_PATH = os.path.join(SKY130_SCL, "sky130_scl_9T")
            lib_corner_files[STDCELL_LIBRARY_BASE_PATH] = os.listdir(
                os.path.join(STDCELL_LIBRARY_BASE_PATH, "lib")
            )
            lib_corner_files[STDCELL_LIBRARY_BASE_PATH].sort()
            
            # Generate stackup
            metals = []  # type: List[Metal]

            tlef_path = os.path.join(SKY130_SCL, "sky130_scl_9T_tech", "lef", f"{slib}_9T.tlef")
            metals = list(
                map(lambda m: Metal.model_validate(m), LEFUtils.get_metals(tlef_path))
            )
            
            # The Cadence SCL routing pitches are larger than min_width + DRC min_spacing.
            # Hammer's TWWT power-strap generator requires its first spacing rule to
            # represent the track-aligned spacing: pitch - min_width.
            for metal in metals:
                track_aligned_spacing = metal.pitch - metal.min_width

                metal.power_strap_widths_and_spacings = [
                    rule.model_copy(
                        update={
                            "min_spacing": max(rule.min_spacing,
                            track_aligned_spacing)
                        }
                    )
                    for rule in metal.power_strap_widths_and_spacings
                ]
            
            stackups.append(
                Stackup(name=slib, grid_unit=Decimal("0.001"), metals=metals)
            )

            sites = [
                Site(name="CoreSite", x=Decimal("0.46"), y=Decimal("4.14")),
                Site(name="IOSite", x=Decimal("1.0"), y=Decimal("240.0")),
                Site(name="CornerSite", x=Decimal("240.0"), y=Decimal("240.0")),
            ]

            lvs_decks = [
                LVSDeck(
                    tool_name="pegasus",
                    deck_name="pegasus_lvs",
                    path=self.get_setting("technology.sky130.lvs_deck"),
                )
            ]
            drc_decks = [
                DRCDeck(
                    tool_name="calibre",
                    deck_name="calibre_drc",
                    path="$SKY130_NDA/s8/V2.0.1/DRC/Calibre/s8_drcRules",
                ),
                DRCDeck(
                    tool_name="pegasus",
                    deck_name="pegasus_drc",
                    path=self.get_setting("technology.sky130.drc_deck"),
                ),
            ]
        
        else:
            raise ValueError(f"Incorrect standard cell library selection: {slib}")
        
        
        # add skywater io cells to corners
        io_library_base_path = os.path.join(SKY130A, "libs.ref", "sky130_fd_io") # TODO(jimfang) see commentary near SKY130_IO variable definition
        if os.path.exists(io_library_base_path):
            lib_corner_files[io_library_base_path] = os.listdir(
                os.path.join(io_library_base_path, "lib")
            )
        
        # process corners & register them w/ hammer
        for library_base_path, cornerfiles in lib_corner_files.items():
            for cornerfilename in cornerfiles:
                if "sky130" not in cornerfilename or "#" in cornerfilename:
                    # cadence doesn't use the lib name in their corner libs
                    # also skip random temp files sometimes included in sky130_scl
                    continue
                if "ccsnoise" in cornerfilename:
                    continue  # ignore duplicate corner.lib/corner_ccsnoise.lib files

                tmp = cornerfilename.replace(".lib", "").strip("_nldm")
                if tmp + "_ccsnoise.lib" in lib_corner_files:
                    cornerfilename = (
                        tmp + "_ccsnoise.lib"
                    )  # use ccsnoise version of lib file
                    

                # keep this so that for fd_io, speed/temp/ is processed
                if "sky130A" in library_base_path:
                    split_cell_corner = re.split("_(ff)|_(ss)|_(tt)", tmp)
                    cell_name = split_cell_corner[0]
                    library = tmp.split("__")[0]
                    process = split_cell_corner[1:-1]
                    temp_volt = split_cell_corner[-1].split("_")[1:]

                    if not any(c is not None for c in process):
                        continue

                    # Filter out cross corners (e.g ff_ss or ss_ff)
                    # ignores lib files that has mixed corners such as _ff_ss; if file name is _ss_ss or __tt_tt, reduces to ss or tt.
                    if len(process) > 3:
                        if not functools.reduce(
                            lambda x, y: x and y,
                            map(lambda p, q: p == q, process[0:3], process[4:]),
                            True,
                        ):
                            continue
                    # Determine actual corner
                    speed = next(c for c in process if c is not None).replace("_", "")
                    temp = temp_volt[0]
                    temp = temp.replace("n", "-")
                    temp = temp.split("C")[0] + " C"

                    vdd = (".").join(temp_volt[1].split("v")) + " V"
                    if speed == "ff":
                        speed = "fast"
                    elif speed == "tt":
                        speed = "typical"
                    elif speed == "ss":
                        speed = "slow"
                    else:
                        self.logger.info(
                            "Skipping lib with unsupported corner: {}".format(speed)
                        )
                        continue
                else: 
                    library = "sky130_scl_9T" # TODO(jimfang) support other variants (compact/high speed) of the cdns 9T std cell lib
                    _, speed, vdd, temp, _ = tmp.split("_")

                    # force equivalent operating conditions for speed, since they're different between sky130a and scl
                    # this is needed unless someone regenerates lib characterization for the IO cells at the cadence corners
                    if speed == "ff":
                        temp = "-40 C"
                        vdd = "1.95 V"
                        speed = "fast"
                    if speed == "tt":
                        vdd = "1.80 V"
                        temp = "25 C"
                        speed = "typical"
                    if speed == "ss":
                        vdd = "1.60 V"
                        speed = "slow"
                        temp = "100 C"

                cdl_path = os.path.join(library_base_path, "cdl", library + ".cdl")
                spice_path = os.path.join(
                    library_base_path, "spice", library + ".spice"
                )

                # just prioritize spice, arbitrary choice
                # assert not (os.path.exists(cdl_path) and os.path.exists(spice_path)), "both spice and cdl netlists exist! this is ambiguous :("
                netlist_path = spice_path if os.path.exists(spice_path) else cdl_path

                if slib == "sky130_fd_sc_hd": 
                    lib_entry = Library(
                        nldm_liberty_file=os.path.join(
                            library_base_path, "lib", cornerfilename
                        ),
                        verilog_sim=os.path.join(
                            library_base_path,
                            "verilog",
                            library + ".v" # sky130_fd_sc_hd.v
                        ),
                        lef_file = (
                            "cache/sky130_ef_io.lef"
                            if library == "sky130_ef_io"
                            else os.path.join(library_base_path, "lef", library + ".lef")
                        ), # we modify sky130_ef_io.lef in setup_io_lefs(), so use the modified version if we are adding sky130_ef_io collateral
                        spice_file=netlist_path,
                        gds_file=os.path.join(library_base_path, "gds", library + ".gds"),
                        corner=Corner(nmos=speed, pmos=speed, temperature=temp),
                        supplies=Supplies(VDD=vdd, GND="0 V"),
                        provides=[Provide(lib_type="stdcell", vt="RVT")], # RVT = SVT
                    )
                    libs.append(lib_entry)
                    
                elif slib == "sky130_scl":
                    # Cadence PDK transistor models (.lib section per corner) for the SCL
                    # netlists, used by Spectre to characterize Voltus PG views
                    spice_model_file = None
                    scl_models = os.path.join(SKY130_CDS, "models", "sky130.lib.spice")
                    if library == "sky130_scl_9T" and os.path.exists(scl_models):
                        spice_model_file = SpiceModelFile(
                            path=scl_models,
                            lib_corner={"fast": "ff", "typical": "tt", "slow": "ss"}[speed],
                        )

                    lib_entry = Library(
                        nldm_liberty_file=os.path.join(
                            library_base_path, "lib", cornerfilename
                        ),
                        verilog_sim=os.path.join(
                            library_base_path,
                            "verilog",
                            library + ".v" # sky130_scl_9T.v
                        ),
                        lef_file = (
                            "cache/sky130_ef_io.lef"
                            if library == "sky130_ef_io"
                            else os.path.join(library_base_path, "lef", library + ".lef")
                        ), # we modify sky130_ef_io.lef in setup_io_lefs(), so use the modified version if we are adding sky130_ef_io collateral
                        spice_file=netlist_path,
                        spice_model_file=spice_model_file,
                        gds_file=os.path.join(library_base_path, "gds", library + ".gds"),
                        corner=Corner(nmos=speed, pmos=speed, temperature=temp),
                        supplies=Supplies(VDD=vdd, GND="0 V"),
                        provides=[Provide(lib_type="stdcell", vt="RVT")], # RVT = SVT
                    )
                    libs.append(lib_entry)

                    if library == "sky130_scl_9T":
                        # Netlists for SCL cells the vendor CDL lacks, per corner with the same models.
                        # Only for PG-library characterization: these are physical-only cells, so LVS
                        # and the other design netlist consumers must not read them.
                        libs += [
                            Library(
                                spice_file=path,
                                spice_model_file=spice_model_file,
                                corner=Corner(nmos=speed, pmos=speed, temperature=temp),
                                supplies=Supplies(VDD=vdd, GND="0 V"),
                                provides=[Provide(lib_type="pg_characterization")],
                            )
                            for path in self.get_setting("technology.sky130.sky130_scl_extra_spice") or []
                        ]

                if "sky130_fd_io" in library_base_path: # ex: /scratch/jfx/open-pdks/sky130/sky130A/libs.ref/sky130_fd_io
                    # these are seperate from the io gds
                    # the story is:
                    # sky130_fd_io is the skywater provided base I/O library
                    # sky130_ef_io is the efabless/open_pdks (== sky130A) addendum, which does the following:
                        # (1) Changes the orientation of the corner pad from upper-right to
                        #     lower-left with a wrapper cell called "sky130_fd_io__corner_pad".  Also
                        #     extends the power buses to make the dimensions of the corner pad
                        #     multiples of 1um.
                        #
                        # (2) Adds a 1um-wide spacer cell to complement the existing 5um-wide
                        #     spacer cell.
                        #
                        # (3) Adds wrappers for all the combinations of power pad base cell +
                        #     power pad overlay, to create all 12 combinations, for pads with
                        #     either high- or low-voltage clamps, connecting to one of the six
                        #     power domains vddio, vdda, vccd, vssio, vssa, or vssd.
                        #
                        # (4) Fix a DRC error in the SkyWater GPIO pad layout
                        #
                        # Source: https://github.com/fossi-foundation/open-pdks/tree/main/sky130/custom/sky130_fd_io
                    # sky130_ef_io instantiates/uses the underlying sky130_fd_io collateral (https://github.com/fossi-foundation/skywater-pdk-libs-sky130_fd_io), which depends on the primative devices library (https://github.com/fossi-foundation/skywater-pdk-libs-sky130_fd_pr)
                    # therefore, in order to use these IO cells, at least the above 2 should be installed. As a safety, we should just install all of OpenPDKs
                    
                    extra_gds_files = [
                        "sky130_ef_io__analog.gds",
                        "sky130_ef_io__disconnect_vccd_slice_5um.gds",
                        "sky130_ef_io__gpiov2_pad_wrapped.gds",
                        "sky130_ef_io__bare_pad.gds",
                        "sky130_ef_io__disconnect_vdda_slice_5um.gds",
                        "sky130_ef_io__connect_vcchib_vccd_and_vswitch_vddio_slice_20um.gds",
                        "sky130_ef_io__connect_vdda_vddio_and_vssa_vssio_slice_20um.gds",
                        "sky130_ef_io.gds",
                    ]
                    
                    for extra_gds_file in extra_gds_files:
                        lib_entry = Library(
                            nldm_liberty_file=os.path.join(
                                io_library_base_path, "lib", cornerfilename # TODO(jimfang) this as far as i can tell imports all avail lib files under sky130_fd_io... is this going to cause conflicts?
                            ),
                            verilog_sim=os.path.join(
                                io_library_base_path,
                                "verilog",
                                "sky130_fd_io.v"
                            ),
                            lef_file=os.path.join(
                                io_library_base_path, "lef", "sky130_fd_io.lef"
                            ),
                            spice_file=os.path.join(io_library_base_path, "spice", "sky130_fd_io.spice"),
                            gds_file=os.path.join(
                                io_library_base_path, "gds", extra_gds_file
                            ),
                            corner=Corner(nmos=speed, pmos=speed, temperature=temp),
                            supplies=Supplies(VDD=vdd, GND="0 V"),
                            provides=[Provide(lib_type="iocell", vt="RVT")],
                        )
                        libs.append(lib_entry)
                        
                    # add ef_io cell's lef files (one time is enough since this isn't specific to the particular gds)
                    lib_entry = Library(
                        lef_file="cache/sky130_ef_io.lef",
                        provides=[Provide(lib_type="iocell", vt="RVT")],
                    )
                    libs.append(lib_entry)
        
        if slib == "sky130_fd_sc_hd":
            # add primitives.v which sky130_fd_sc_hd depends on (once only since it only needs to be included once to be able to be referenced)
            lib_entry = Library(
                verilog_sim=os.path.join(
                    library_base_path,
                    "verilog",
                    "primitives.v" # /open-pdks/sky130/sky130A/libs.ref/sky130_fd_sc_hd/verilog/primitives.v
                ),
                provides=[Provide(lib_type="stdcell", vt="RVT")], # RVT = SVT
            )
            libs.append(lib_entry)

        # Neither PDK IO Verilog file is usable for simulation as shipped:
        # sky130_ef_io.v does not compile, and sky130_fd_io.v corrupts its pad
        # outputs to X (see extra/sim/README.md). Simulation-only replacements
        # live in extra/sim/ and are named after the file they stand in for.
        sim_model_dir = os.path.join(os.path.dirname(__file__), "extra", "sim")
        for lib in libs:
            if lib.verilog_sim and os.path.basename(lib.verilog_sim) in ("sky130_fd_io.v", "sky130_ef_io.v"):
                lib.verilog_sim = os.path.join(sim_model_dir, os.path.basename(lib.verilog_sim))

        self.config = TechJSON(
            name="Skywater 130nm Library",
            grid_unit="0.001",
            shrink_factor=None,
            installs=[
                PathPrefix(id="$SKY130_NDA", path="technology.sky130.sky130_nda"),
                PathPrefix(id="$SKY130A", path="technology.sky130.sky130A"),
                PathPrefix(id="$SKY130_CDS", path="technology.sky130.sky130_cds"),
                PathPrefix(id="$SKY130_SCL", path="technology.sky130.sky130_scl"),
            ],
            libraries=libs,
            gds_map_file="sky130_lefpin.map",
            physical_only_cells_list=phys_only,
            dont_use_list=dont_use,
            additional_drc_text="",
            lvs_decks=lvs_decks,
            drc_decks=drc_decks,
            additional_lvs_text="",
            tarballs=None,
            sites=sites,
            stackups=stackups,
            special_cells=spcl_cells,
            extra_prefixes=None,
        )

        self.library_name = slib
        
    
    def get_extra_libraries(self) -> List[ExtraLibrary]:
        """Redirect the Caravel POR macro at our own simulation model.

        Designs on a Caravel-style pad ring declare simple_por in
        vlsi.technology.extra_libraries, because the macro is not part of the
        sky130 PDK proper. The behavioral model Caravel ships with it cannot be
        simulated as instantiated, for three independent reasons:

          * It references vdd3v3 inside `always @(posedge vdd3v3)` but only
            declares it under `ifdef USE_POWER_PINS, and the file sets
            `default_nettype none -- so without the define it does not compile.
          * With the define it still does not work: designs connect only the
            three signal ports, so vdd3v3 sits at Z, there is never a posedge,
            and porb_h stays low forever. porb_h drives ENABLE_H on every IO
            cell, so the whole pad ring would be held disabled.
          * It instantiates sky130_fd_sc_hvl__schmittbuf_1 and
            sky130_fd_sc_hvl__lsbufhv2lv_1, which would require the hvl library
            models in the liblist as well.

        extra/sim/simple_por.v reproduces the model's polarity and 500 ns POR
        ramp over just the three signal ports. Redirecting here rather than in
        the design config keeps the path out of user YAML and applies it to
        every flow step, including `redo-` steps replaying an older config
        snapshot.

        Narrowly matched -- lib_type "por" whose verilog_sim is the PDK's
        simple_por.v -- so a design supplying a working model of its own, or a
        different POR macro, is left alone.
        """
        libs = super().get_extra_libraries()
        model = os.path.join(
            os.path.dirname(__file__), "extra", "sim", "simple_por.v"
        )
        for extra_lib in libs:
            lib = extra_lib.library
            provides_por = any(
                p.lib_type == "por" for p in (lib.provides or [])
            )
            if provides_por and os.path.basename(lib.verilog_sim or "") == "simple_por.v":
                lib.verilog_sim = model
        return libs

    def post_install_script(self) -> None:
        # check whether variables were overriden to point to a valid path
        if self.get_setting("technology.sky130.stdcell_library") == "sky130_fd_sc_hd":
            self.setup_cdl()
            self.setup_verilog()
        self.setup_techlef()
        self.setup_io_lefs()
        self.setup_calibre_lvs_deck()
        self.setup_hvl_ls_lef()
        self.logger.info('Loaded Sky130 Tech')


    def setup_cdl(self) -> None:
        """Copy and hack the cdl, replacing pfet_01v8_hvt/nfet_01v8 with
        respective names in LVS deck
        """
        setting_dir = self.get_setting("technology.sky130.sky130A")
        setting_dir = Path(setting_dir)
        source_path = (
            setting_dir
            / "libs.ref"
            / self.library_name
            / "cdl"
            / f"{self.library_name}.cdl"
        )
        if not source_path.exists():
            raise FileNotFoundError(f"CDL not found: {source_path}")

        cache_tech_dir_path = Path(self.cache_dir)
        os.makedirs(cache_tech_dir_path, exist_ok=True)
        dest_path = cache_tech_dir_path / f"{self.library_name}.cdl"

        # device names expected in LVS decks
        if self.get_setting("vlsi.core.lvs_tool") == "hammer.lvs.calibre":
            pmos = "phighvt"
            nmos = "nshort"
        elif self.get_setting("vlsi.core.lvs_tool") == "hammer.lvs.pegasus":
            pmos = "pfet_01v8_hvt"
            nmos = "nfet_01v8"
        elif self.get_setting("vlsi.core.lvs_tool") == "hammer.lvs.netgen":
            pmos = "sky130_fd_pr__pfet_01v8_hvt"
            nmos = "sky130_fd_pr__nfet_01v8"
        else:
            shutil.copy2(source_path, dest_path)
            return

        with open(source_path, "r") as sf:
            with open(dest_path, "w") as df:
                self.logger.info(
                    "Modifying CDL netlist: {} -> {}".format(source_path, dest_path)
                )
                df.write("*.SCALE MICRON\n")
                for line in sf:
                    line = line.replace("pfet_01v8_hvt", pmos)
                    line = line.replace("nfet_01v8", nmos)
                    df.write(line)

    # Copy and hack the verilog
    #   - primitives.v: set default nettype to 'wire' instead of 'none'
    #           (the open-source RTL sim tools don't treat undeclared signals as errors)
    def setup_verilog(self) -> None:
        setting_dir = self.get_setting("technology.sky130.sky130A")
        setting_dir = Path(setting_dir)
        
        # primitives.v
        source_path = (
            setting_dir / "libs.ref" / self.library_name / "verilog" / "primitives.v"
        )
        if not source_path.exists():
            raise FileNotFoundError(f"Verilog not found: {source_path}")

        cache_tech_dir_path = Path(self.cache_dir)
        os.makedirs(cache_tech_dir_path, exist_ok=True)
        dest_path = cache_tech_dir_path / "primitives.v"

        with open(source_path, "r") as sf:
            with open(dest_path, "w") as df:
                self.logger.info(
                    "Modifying Verilog netlist: {} -> {}".format(source_path, dest_path)
                )
                for line in sf:
                    line = line.replace(
                        "`default_nettype none", "`default_nettype wire"
                    )
                    df.write(line)

    # Copy and hack the tech-lef, adding this very important `licon` section
    # see comments near _additional_tlef_edit_for_scl section.
    def setup_techlef(self) -> None:
        cache_tech_dir_path = Path(self.cache_dir)
        os.makedirs(cache_tech_dir_path, exist_ok=True)
        if self.get_setting("technology.sky130.stdcell_library") == "sky130_fd_sc_hd":
            setting_dir = self.get_setting("technology.sky130.sky130A")
            setting_dir = Path(setting_dir)
            source_path = (
                setting_dir
                / "libs.ref"
                / self.library_name
                / "techlef"
                / f"{self.library_name}__nom.tlef"
            )
            dest_path = cache_tech_dir_path / f"{self.library_name}__nom.tlef"
        else:
            setting_dir = self.get_setting("technology.sky130.sky130_scl")
            setting_dir = Path(setting_dir)
            source_path = setting_dir / "sky130_scl_9T_tech" /  "lef" / "sky130_scl_9T.tlef"
            dest_path = cache_tech_dir_path / "sky130_scl_9T.tlef"
        if not source_path.exists():
            raise FileNotFoundError(f"Tech-LEF not found: {source_path}")

        with open(source_path, "r") as sf:
            with open(dest_path, "w") as df:
                self.logger.info(
                    "Modifying Technology LEF: {} -> {}".format(source_path, dest_path)
                )
                for line in sf:
                    df.write(line)
                    if (
                        self.get_setting("technology.sky130.stdcell_library")
                        == "sky130_scl"
                    ):
                        if line.strip() == "END poly":
                            df.write(_additional_tlef_edit_for_scl)

    # Power pins for clamps must be CLASS CORE - annotation is needed by innovus to mark the all clamp's met3 power port to be intended for core-side connection (as opposed to ring side -- which is inferred by innovus in absence of this annotation)
    #     pad-ring side                         core side
    #     VDDIO/VSSIO ring ── clamp ── VCCD1/VSSD1 tails
    #     PORT                         PORT CLASS CORE
    # connect/disconnect spacers must be CLASS PAD SPACER, not AREAIO - known bug, see some fixes already commited here: https://github.com/fossi-foundation/open-pdks/commit/d815bb30c9afdf9e264c276a8a2b533108dea3d0
    # add ANTENNAGATEAREA 1.529 for met3 => total MOS gate-oxide area electrically connected to that PIN -- cannot confirm the source of 1.529 number.
    # def setup_io_lefs(self) -> None:
    #     sky130A_path = Path(self.get_setting("technology.sky130.sky130A"))
    #     source_path = (
    #         sky130A_path / "libs.ref" / "sky130_fd_io" / "lef" / "sky130_ef_io.lef"
    #     )
    #     if not source_path.exists():
    #         raise FileNotFoundError(f"IO LEF not found: {source_path}")

    #     cache_tech_dir_path = Path(self.cache_dir)
    #     os.makedirs(cache_tech_dir_path, exist_ok=True)
    #     dest_path = cache_tech_dir_path / "sky130_ef_io.lef"

    #     with open(source_path, "r") as sf:
    #         with open(dest_path, "w") as df:
    #             self.logger.info(
    #                 "Modifying IO LEF: {} -> {}".format(source_path, dest_path)
    #             )
    #             sl = sf.readlines()
    #             for net in ["VCCD1", "VSSD1", "VDDA", "VSSA", "VSSIO"]:
    #                 start = [idx for idx, line in enumerate(sl) if "PIN " + net in line]
    #                 end = [idx for idx, line in enumerate(sl) if "END " + net in line]
    #                 intervals = zip(start, end)
    #                 for intv in intervals:
    #                     port_idx = [
    #                         idx
    #                         for idx, line in enumerate(sl[intv[0] : intv[1]])
    #                         if "PORT" in line and "met3" in sl[intv[0] + idx + 1]
    #                     ]
    #                     for idx in port_idx:
    #                         sl[intv[0] + idx] = sl[intv[0] + idx].replace(
    #                             "PORT", "PORT\n      CLASS CORE ;"
    #                         )
    #             # force class to spacer
    #             for macro_name in [
    #                 "sky130_ef_io__disconnect_vccd_slice_5um",
    #                 "sky130_ef_io__disconnect_vdda_slice_5um",
    #                 "sky130_ef_io__connect_vcchib_vccd_and_vswitch_vddio_slice_20um",
    #             ]:
    #                 start = [
    #                     idx
    #                     for idx, line in enumerate(sl)
    #                     if f"MACRO {macro_name}" in line
    #                 ]
    #                 sl[start[0] + 1] = sl[start[0] + 1].replace("AREAIO", "SPACER")

    #             for idx, line in enumerate(sl):
    #                 if "PIN OUT" in line:
    #                     sl[idx + 1].replace(
    #                         "DIRECTION INPUT ;",
    #                         "DIRECTION INPUT ;\n    ANTENNAGATEAREA 1.529 LAYER met3 ;",
    #                     )

    #             df.writelines(sl)
    
    def setup_io_lefs(self) -> None:
        """
        Prepare a modified sky130_ef_io LEF for Innovus.

        Modifications:
        1. Mark met3 PORTs of selected dedicated PAD POWER pins as CLASS CORE.
        Innovus sRoute uses this annotation to distinguish the
        core-facing power ports from the pad-ring-facing ports.

        This applies to both clamped and non-clamped dedicated power pads,
        but NOT to arbitrary IO macros, GPIOs, spacers, corner cells, etc.

            pad-ring side                         core side
            M4/M5 IO buses -- power pad -- M3 power tail
            ordinary PORT               PORT CLASS CORE

        2. Force selected connect/disconnect spacer cells to
        CLASS PAD SPACER instead of CLASS PAD AREAIO.

        3. Add ANTENNAGATEAREA 1.529 LAYER met3 to PIN OUT entries.

        The resulting LEF is written into the Hammer technology cache.
        """

        sky130A_path = Path(self.get_setting("technology.sky130.sky130A"))
        source_path = (
            sky130A_path
            / "libs.ref"
            / "sky130_fd_io"
            / "lef"
            / "sky130_ef_io.lef"
        )

        if not source_path.exists():
            raise FileNotFoundError(f"IO LEF not found: {source_path}")

        cache_tech_dir_path = Path(self.cache_dir)
        os.makedirs(cache_tech_dir_path, exist_ok=True)

        dest_path = cache_tech_dir_path / "sky130_ef_io.lef"

        self.logger.info(
            "Modifying IO LEF: {} -> {}".format(source_path, dest_path)
        )

        with open(source_path, "r") as sf:
            sl = sf.readlines()

        source_core_count = "".join(sl).count("CLASS CORE ;")
        self.logger.info(
            "IO LEF source CLASS CORE count: {}".format(source_core_count)
        )

        # ------------------------------------------------------------------
        # Identify dedicated CLASS PAD POWER macros.
        #
        # Do not restrict this to "_clamped" macros: non-clamped dedicated
        # supply pads also have core-facing met3 power ports which need the
        # same CLASS CORE annotation.
        #
        # At the same time, do not apply the modification to every occurrence
        # of VDDIO/VSSIO/VCCD/etc. in the entire IO library. Only dedicated
        # PAD POWER macros are eligible.
        # ------------------------------------------------------------------

        pad_power_macros = set()

        current_macro = None

        for line in sl:
            stripped = line.strip()

            if stripped.startswith("MACRO "):
                parts = stripped.split()
                current_macro = parts[1] if len(parts) >= 2 else None
                continue

            if (
                current_macro is not None
                and stripped == "CLASS PAD POWER ;"
            ):
                pad_power_macros.add(current_macro)
                continue

            if (
                current_macro is not None
                and stripped == f"END {current_macro}"
            ):
                current_macro = None

        self.logger.info(
            "IO LEF: found {} CLASS PAD POWER macros".format(
                len(pad_power_macros)
            )
        )

        # ------------------------------------------------------------------
        # Mark core-facing met3 PG ports as CLASS CORE.
        #
        # Selection is deliberately constrained to:
        #
        #   1. Macro is CLASS PAD POWER.
        #   2. Exact PIN name is one of the known supply pins below.
        #   3. The individual PORT contains met3 geometry.
        #
        # This means:
        #
        #   dedicated VDDIO/VSSIO/VCCD/VSSD/etc. pads  -> eligible
        #   clamped dedicated supply pads              -> eligible
        #   non-clamped dedicated supply pads          -> eligible
        #   GPIO / signal pads                         -> excluded
        #   com_bus/connect/disconnect spacers          -> excluded
        #   corner/endcap cells                        -> excluded
        #
        # Exact PIN matching is important. For example, "VSSIO" must not
        # accidentally match VSSIO_Q.
        # ------------------------------------------------------------------

        core_pin_names = {
            "VCCD",
            "VCCD1",
            "VSSD",
            "VSSD1",
            "VDDA",
            "VSSA",
            "VDDIO",
            "VSSIO",
        }

        core_ports_added = 0
        current_macro = None

        i = 0
        while i < len(sl):
            stripped = sl[i].strip()

            # Track which macro this PIN belongs to.
            if stripped.startswith("MACRO "):
                parts = stripped.split()
                current_macro = parts[1] if len(parts) >= 2 else None
                i += 1
                continue

            if (
                current_macro is not None
                and stripped == f"END {current_macro}"
            ):
                current_macro = None
                i += 1
                continue

            # Match an exact LEF PIN declaration.
            if stripped.startswith("PIN "):
                parts = stripped.split()
                pin_name = parts[1] if len(parts) >= 2 else None

                if (
                    current_macro in pad_power_macros
                    and pin_name in core_pin_names
                ):
                    # Find the exact END <pin_name> corresponding to this PIN.
                    pin_end = i + 1

                    while pin_end < len(sl):
                        if sl[pin_end].strip() == f"END {pin_name}":
                            break
                        pin_end += 1

                    if pin_end >= len(sl):
                        raise RuntimeError(
                            f"Malformed IO LEF: could not find END {pin_name} "
                            f"after line {i + 1} in macro {current_macro}"
                        )

                    # Walk through each PORT belonging to this PIN.
                    j = i + 1

                    while j < pin_end:
                        if sl[j].strip() != "PORT":
                            j += 1
                            continue

                        # Locate the END of this PORT.
                        port_end = j + 1

                        while port_end < pin_end:
                            if sl[port_end].strip() == "END":
                                break
                            port_end += 1

                        if port_end >= pin_end:
                            raise RuntimeError(
                                f"Malformed IO LEF: unterminated PORT in "
                                f"{current_macro}/{pin_name} near line {j + 1}"
                            )

                        # A PORT may contain more than one LAYER statement.
                        # Mark it CORE if any of its geometry is on met3.
                        has_met3 = False
                        already_core = False

                        for n in range(j + 1, port_end):
                            s = sl[n].strip()

                            if s == "CLASS CORE ;":
                                already_core = True

                            if s.startswith("LAYER "):
                                layer_parts = s.split()

                                if len(layer_parts) >= 2:
                                    layer_name = layer_parts[1].rstrip(";")

                                    if layer_name == "met3":
                                        has_met3 = True

                        if has_met3 and not already_core:
                            # Preserve the PORT indentation and insert
                            # CLASS CORE immediately after PORT.
                            indent = sl[j][
                                : len(sl[j]) - len(sl[j].lstrip())
                            ]

                            sl[j] = (
                                f"{indent}PORT\n"
                                f"{indent}  CLASS CORE ;\n"
                            )

                            core_ports_added += 1

                            self.logger.debug(
                                "IO LEF: marked {}/{} met3 PORT "
                                "as CLASS CORE".format(
                                    current_macro,
                                    pin_name,
                                )
                            )

                        j = port_end + 1

                    i = pin_end

            i += 1

        self.logger.info(
            "IO LEF: added CLASS CORE to {} met3 PAD POWER PORTs".format(
                core_ports_added
            )
        )

        # ------------------------------------------------------------------
        # Force connect/disconnect cells to be PAD SPACER rather than AREAIO.
        #
        # Known Open-PDKs issue/fix:
        # https://github.com/fossi-foundation/open-pdks/commit/d815bb30c9afdf9e264c276a8a2b533108dea3d0
        # ------------------------------------------------------------------

        spacer_macro_names = [
            "sky130_ef_io__disconnect_vccd_slice_5um",
            "sky130_ef_io__disconnect_vdda_slice_5um",
            "sky130_ef_io__connect_vcchib_vccd_and_vswitch_vddio_slice_20um",
        ]

        for macro_name in spacer_macro_names:
            macro_start = None

            for idx, line in enumerate(sl):
                if line.strip() == f"MACRO {macro_name}":
                    macro_start = idx
                    break

            if macro_start is None:
                raise RuntimeError(
                    f"Could not find IO macro {macro_name} in {source_path}"
                )

            # CLASS is expected near the beginning of the macro, but search a
            # short distance rather than blindly assuming macro_start + 1.
            class_found = False

            for idx in range(
                macro_start + 1,
                min(macro_start + 10, len(sl)),
            ):
                stripped = sl[idx].strip()

                if stripped.startswith("CLASS "):
                    sl[idx] = sl[idx].replace("AREAIO", "SPACER")
                    class_found = True
                    break

                # Do not accidentally run into another macro.
                if stripped.startswith("MACRO "):
                    break

            if not class_found:
                raise RuntimeError(
                    f"Could not find CLASS statement for IO macro {macro_name}"
                )

        # ------------------------------------------------------------------
        # Add antenna gate area annotation to PIN OUT.
        #
        # The previous implementation called str.replace() without assigning
        # its return value, so the LEF was never actually modified.
        # ------------------------------------------------------------------

        antenna_count = 0

        for idx, line in enumerate(sl):
            if line.strip() != "PIN OUT":
                continue

            # Find the DIRECTION statement belonging to this PIN.
            pin_end = idx + 1

            while pin_end < len(sl):
                if sl[pin_end].strip() == "END OUT":
                    break
                pin_end += 1

            for direction_idx in range(idx + 1, pin_end):
                if sl[direction_idx].strip() == "DIRECTION INPUT ;":
                    indent = sl[direction_idx][
                        : len(sl[direction_idx])
                        - len(sl[direction_idx].lstrip())
                    ]

                    # Don't add a duplicate annotation if this source LEF
                    # already contains one.
                    already_has_antenna = any(
                        "ANTENNAGATEAREA 1.529 LAYER met3 ;" in sl[n]
                        for n in range(direction_idx + 1, pin_end)
                    )

                    if not already_has_antenna:
                        sl[direction_idx] = (
                            f"{indent}DIRECTION INPUT ;\n"
                            f"{indent}ANTENNAGATEAREA 1.529 LAYER met3 ;\n"
                        )
                        antenna_count += 1

                    break

        self.logger.info(
            "IO LEF: added ANTENNAGATEAREA to {} PIN OUT entries".format(
                antenna_count
            )
        )

        # ------------------------------------------------------------------
        # Write modified LEF.
        # ------------------------------------------------------------------

        with open(dest_path, "w") as df:
            df.writelines(sl)

        # ------------------------------------------------------------------
        # Validate the generated cache LEF.
        #
        # If this file contains CLASS CORE but the LEF copied into par-rundir
        # does not, the corruption/replacement occurred after this step.
        # ------------------------------------------------------------------

        output_text = dest_path.read_text()
        output_core_count = output_text.count("CLASS CORE ;")

        self.logger.info(
            "IO LEF cache path: {}".format(dest_path)
        )
        self.logger.info(
            "IO LEF output CLASS CORE count: {}".format(output_core_count)
        )

        if output_core_count == 0:
            raise RuntimeError(
                "setup_io_lefs generated an IO LEF with zero "
                f"CLASS CORE annotations: {dest_path}"
            )

        if core_ports_added == 0 and source_core_count == 0:
            raise RuntimeError(
                "setup_io_lefs did not find any eligible met3 PAD POWER "
                "PORTs requiring CLASS CORE annotation"
            )

        # ------------------------------------------------------------------
        # Explicit validation of known core-facing power-pad geometries.
        #
        # These cover both the original VSSA failure and the later VDDIO/VCCD
        # failures seen in Innovus connectivity checking.
        # ------------------------------------------------------------------

        expected_core_ports = {
            "VSSA port 1": (
                "PORT\n"
                "      CLASS CORE ;\n"
                "      LAYER met3 ;\n"
                "        RECT 0.495 -2.035 24.395 30.480 ;"
            ),
            "VSSA port 2": (
                "PORT\n"
                "      CLASS CORE ;\n"
                "      LAYER met3 ;\n"
                "        RECT 50.390 -2.035 74.290 34.725 ;"
            ),
            "VDDIO port 1": (
                "PORT\n"
                "      CLASS CORE ;\n"
                "      LAYER met3 ;\n"
                "        RECT 0.495 -2.035 24.395 17.765 ;"
            ),
            "VDDIO port 2": (
                "PORT\n"
                "      CLASS CORE ;\n"
                "      LAYER met3 ;\n"
                "        RECT 50.390 -2.035 74.290 17.765 ;"
            ),
            "VCCD port 1": (
                "PORT\n"
                "      CLASS CORE ;\n"
                "      LAYER met3 ;\n"
                "        RECT 0.500 -0.035 24.500 6.865 ;"
            ),
            "VCCD port 2": (
                "PORT\n"
                "      CLASS CORE ;\n"
                "      LAYER met3 ;\n"
                "        RECT 50.755 -0.035 74.700 6.865 ;"
            ),
        }

        for description, expected_text in expected_core_ports.items():
            if expected_text not in output_text:
                raise RuntimeError(
                    "Generated IO LEF is missing CLASS CORE on known "
                    f"core-facing {description}"
                )

        self.logger.info(
            "IO LEF validation passed: known VSSA/VDDIO/VCCD "
            "core-facing met3 ports are CLASS CORE"
        )

    def setup_hvl_ls_lef(self) -> bool:
        # Treat HVL cells as if they were hard macros to avoid needing to set them
        # up "properly" with multiple power domains
        # does 2 things:
        # strips "SITE unithv ;" across all cells/MACROs
        # converts "CLASS CORE ;" -> "CLASS BLOCK ;" - hard macro each cell
        
        # iterating through all the cells is intentional, since recent PDK versions ship all the cells in 1 GDS file; if we only pulled out the level shifter lef into its own file, we would need to extract that 1 cell into a new GDS (would need to manually do this every PDK update, not sustainable).
        # We can include all the HVL collateral, but will only instantiate the level shifter in the hammer design yaml.

        # TODO(jimfang) BEFORE PROD: place edited level shifter collat in hammer plugin folder, then change this path
        source_path = Path(self.get_setting("technology.sky130.misc_tapeout_collateral")) / "OPEN-PDKS-Modifications" / "sky130_fd_sc_hvl__lsbufhv2lv_1_m1_access" / "sky130_fd_sc_hvl__lsbufhv2lv_1.lef"
        
        lef_name = "sky130_fd_sc_hvl__lsbufhv2lv_1.lef"
        cache_path = Path(self.cache_dir) / "fd_sc_hvl__lef" / lef_name # will be used in design.yaml & correlated to the sky130_fd_sc_hvl gds
        cache_path.parent.mkdir(exist_ok=True)

        with source_path.open("r") as sf, cache_path.open("w") as df:
            self.logger.info(f"Patching HVL Level Shifter LEF: {source_path} -> {cache_path}")
            is_in_site_def = False
            is_in_macro_def = False
            for line in sf:
                if is_in_site_def:
                    if "END unithv" in line:
                        is_in_site_def = False
                elif not is_in_macro_def and "SITE unithv" in line:
                    is_in_site_def = True
                elif "MACRO " in line:
                    is_in_macro_def = True
                    df.write(line)
                elif "SITE unithv" in line:
                    pass
                else:
                    df.write(
                        line.replace("CLASS CORE", "CLASS BLOCK")
                        if not (("ANTENNACELL" in line) or ("SPACER" in line))
                        else line
                    )
    
    def setup_calibre_lvs_deck(self) -> bool:
        # Remove conflicting specification statements found in PDK LVS decks
        pattern = ".*({}).*\n".format("|".join(LVS_DECK_SCRUB_LINES))
        matcher = re.compile(pattern)

        source_paths = self.get_setting("technology.sky130.lvs_deck_sources")
        lvs_decks = self.config.lvs_decks
        if not lvs_decks:
            return True
        for i, deck in enumerate(lvs_decks):
            if deck.tool_name != "calibre":
                continue
            try:
                source_path = Path(source_paths[i])
            except IndexError:
                self.logger.error(
                    "No corresponding source for LVS deck {}".format(deck)
                )
                continue
            if not source_path.exists():
                raise FileNotFoundError(f"LVS deck not found: {source_path}")
            cache_tech_dir_path = Path(self.cache_dir)
            dest_path = os.path.join(cache_tech_dir_path, os.path.basename(deck.path))
            with open(source_path, "r") as sf:
                with open(dest_path, "w") as df:
                    self.logger.info(
                        "Modifying LVS deck: {} -> {}".format(source_path, dest_path)
                    )
                    df.write(matcher.sub("", sf.read()))
                    df.write(LVS_DECK_INSERT_LINES)
        return True

    def get_tech_par_hooks(self, tool_name: str) -> List[HammerToolHookAction]:
        hooks = {
            "innovus": [
                HammerTool.make_post_insertion_hook(
                    "init_design", sky130_innovus_settings
                ),
                HammerTool.make_pre_insertion_hook("power_straps", sky130_connect_nets),
                HammerTool.make_pre_insertion_hook(
                    "write_design", sky130_connect_nets2
                ),
            ]
        }
        # there are no cap/decap cells in the cadence stdcell library as of version 0.0.3, so we can't do things that reference them
        if self.get_setting("technology.sky130.stdcell_library") == "sky130_scl":
            hooks["innovus"].extend(
                [
                    HammerTool.make_pre_insertion_hook(
                        "power_straps", power_rail_straps_no_tapcells
                    ),
                    # TODO(jimfang) can we remove this now? if tools can recognize clock buffer cells
                    # HammerTool.make_pre_insertion_hook(
                    #     "clock_tree", set_cts_base_cells
                    # ),
                ]
            )
        else:
            hooks["innovus"].append(
                HammerTool.make_pre_insertion_hook(
                    "place_tap_cells", sky130_add_endcaps
                )
            )

        return hooks.get(tool_name, [])

    def get_tech_drc_hooks(self, tool_name: str) -> List[HammerToolHookAction]:
        calibre_hooks = []
        pegasus_hooks = []
        if self.get_setting("technology.sky130.drc_blackbox_srams"):
            calibre_hooks.append(
                HammerTool.make_post_insertion_hook(
                    "generate_drc_run_file", calibre_drc_blackbox_srams
                )
            )
            pegasus_hooks.append(
                HammerTool.make_post_insertion_hook(
                    "generate_drc_ctl_file", pegasus_drc_blackbox_srams
                )
            )
        pegasus_hooks.append(
            HammerTool.make_post_insertion_hook(
                "generate_drc_ctl_file", pegasus_drc_blackbox_io_cells
            )
        )
        hooks = {"calibre": calibre_hooks, "pegasus": pegasus_hooks}
        return hooks.get(tool_name, [])

    def get_tech_lvs_hooks(self, tool_name: str) -> List[HammerToolHookAction]:
        calibre_hooks = []
        pegasus_hooks = []
        calibre_hooks.append(
            HammerTool.make_post_insertion_hook(
                "generate_lvs_run_file", sram22_lvs_recognize_gates_all
            )
        )
        if self.get_setting("technology.sky130.lvs_blackbox_srams"):
            calibre_hooks.append(
                HammerTool.make_post_insertion_hook(
                    "generate_lvs_run_file", calibre_lvs_blackbox_srams
                )
            )
            pegasus_hooks.append(
                HammerTool.make_post_insertion_hook(
                    "generate_lvs_ctl_file", pegasus_lvs_blackbox_srams
                )
            )

        if self.get_setting("technology.sky130.stdcell_library") == "sky130_scl":
            pegasus_hooks.append(
                HammerTool.make_post_insertion_hook(
                    "generate_lvs_ctl_file", pegasus_lvs_add_130a_primitives
                )
            )
            if tool_name == "pegasus" and not self.get_setting("technology.sky130.lvs_blackbox_srams"):
                self.logger.warning("Pegasus LVS: the sky130_fd_pr device map has no sram22 bitcell devices; "
                                    "set technology.sky130.lvs_blackbox_srams: true, or sram22 cells will mismatch")
        hooks = {"calibre": calibre_hooks, "pegasus": pegasus_hooks}
        return hooks.get(tool_name, [])

# =============================================================================================

    # TODO(jimfang) this is so hacked up...
    @staticmethod
    def sky130_sram_names() -> List[str]:
        sky130_sram_names = []
        sram_cache_json = importlib.resources.files("hammer.technology.sky130").joinpath("sram-cache.json").read_text()
        dl = json.loads(sram_cache_json)
        for d in dl:
            sky130_sram_names.append(d['name'])
        return sky130_sram_names

# =============================================================================================
# =============================================================================================

# various Innovus database settings
# Innovus Stylus Common UI Text Command Reference 23.17
def sky130_innovus_settings(ht: HammerTool) -> bool:
    assert isinstance(ht, HammerPlaceAndRouteTool), "Innovus settings only for par"
    assert isinstance(ht, TCLTool), "innovus settings can only run on TCL tools"
    """Settings for every tool invocation"""
    ht.append(
        f"""

##########################################################
# Placement attributes  [get_db -category place]
##########################################################
#-------------------------------------------------------------------------------
set_db place_global_place_io_pins true

set_db opt_honor_fences true
set_db place_detail_check_cut_spacing true
set_db place_global_cong_effort high
set_db add_fillers_with_drc false

##########################################################
# Optimization attributes  [get_db -category opt]
##########################################################
#-------------------------------------------------------------------------------

set_db opt_fix_fanout_load true
set_db opt_area_recovery true
set_db opt_post_route_area_reclaim hold_and_setup_aware

##########################################################
# Clock attributes  [get_db -category cts]
##########################################################
#-------------------------------------------------------------------------------
set_db cts_target_skew 0.03
set_db cts_max_fanout 10
#set_db cts_target_max_transition_time .3
set_db opt_setup_target_slack 0.10
set_db opt_hold_target_slack 0.10

##########################################################
# Routing attributes  [get_db -category route]
##########################################################
#-------------------------------------------------------------------------------
set_db route_antenna_diode_insertion true
set_db route_antenna_cell_name "{"sky130_fd_sc_hd__diode_2" if ht.get_setting("technology.sky130.stdcell_library") == "sky130_fd_sc_hd" else "ANTENNA"}"

set_db route_high_freq_search_repair true
set_db route_detail_post_route_spread_wire true
set_db route_with_si_driven true
set_db route_with_timing_driven true
set_db route_concurrent_minimize_via_count_effort high
set_db opt_consider_routing_congestion true
set_db route_detail_use_multi_cut_via_effort medium
    """
    )
    if ht.hierarchical_mode in {HierarchicalMode.Top, HierarchicalMode.Flat}:
        ht.append(
            """
# For top module: snap die to manufacturing grid, not placement grid
set_db floorplan_snap_die_grid manufacturing
set_db floorplan_snap_core_grid manufacturing
set_db floorplan_snap_all_corners_to_grid true
        """
        )

        # ht.append(
        #     """
    # # note this is required for sky130_fd_sc_hd, the design has a ton of drcs if bottom layer is 1
    # # TODO: why is setting routing_layer not enough?
    # set_db design_bottom_routing_layer 2
    # set_db design_top_routing_layer 6
    # # deprected syntax, but this used to always work
    # set_db route_design_bottom_routing_layer 2
    #           """
    # )

    return True

def sky130_connect_nets(ht: HammerTool) -> bool:
    assert isinstance(ht, HammerPlaceAndRouteTool), "connect global nets only for par"
    assert isinstance(ht, TCLTool), "connect global nets can only run on TCL tools"
    for pwr_gnd_net in (ht.get_all_power_nets() + ht.get_all_ground_nets()):
            if pwr_gnd_net.tie is not None:
                ht.append("connect_global_net {tie} -type pg_pin -pin_base_name {net} -all -auto_tie -netlist_override".format(tie=pwr_gnd_net.tie, net=pwr_gnd_net.name))
                ht.append("connect_global_net {tie} -type net    -net_base_name {net} -all -netlist_override".format(tie=pwr_gnd_net.tie, net=pwr_gnd_net.name))
    return True

# Pair VDD/VPWR and VSS/VGND nets
#   these commands are already added in Innovus.write_netlist,
#   but must also occur before power straps are placed
def sky130_connect_nets2(ht: HammerTool) -> bool:
    sky130_connect_nets(ht)
    return True


def power_rail_straps_no_tapcells(ht: HammerTool) -> bool:
    assert not ht.get_setting(
        "par.generate_power_straps_options.by_tracks.generate_rail_layer"
    ), """
Rails must be placed by this hook for sky130_scl!
Set par.generate_power_straps_options.by_tracks.generate_rail_layer: false"""
    #  We do this since there are no explicit tapcells in sky130_scl
    # just need the rail ones, others are placed as usual.
    ht.append(
        """
# Power strap definition for layer met1 (rails):
# should be .14

reset_db -category add_stripes

# M1-only stripe generation. Do not generate vias during this add_stripes
# operation; M1<->M2 vias are added explicitly afterward.
set_db add_stripes_stacked_via_bottom_layer met1
set_db add_stripes_stacked_via_top_layer met1

# set_db add_stripes_spacing_from_block 4.0
# set_db add_stripes_spacing_from_block 0.0 

# set_db add_stripes_ignore_block_check false

# set_db add_stripes_ignore_drc true

set rail_width       0.400
set rail_spacing     3.740
set same_net_pitch   8.280

puts "  rail width:       $rail_width"
puts "  rail spacing:     $rail_spacing"
puts "  same-net pitch:   $same_net_pitch"
puts "  core bbox:        [get_db designs .core_bbox]"

add_stripes \
    -nets {VDD VSS} \
    -layer met1 \
    -direction horizontal \
    -start_from bottom \
    -start_offset \
    -0.200 \
    -width $rail_width \
    -spacing $rail_spacing \
    -set_to_set_distance $same_net_pitch \
    -switch_layer_over_obs false \
    -max_same_layer_jog_length 2.0 \
    -pad_core_ring_top_layer_limit met1 \
    -pad_core_ring_bottom_layer_limit met1 \
    -block_ring_top_layer_limit met1 \
    -block_ring_bottom_layer_limit met1 \
    -use_wire_group 0 \
    -snap_wire_center_to_grid none
    
reset_db -category add_stripes
"""
    )
    return True

def sky130_add_endcaps(ht: HammerTool) -> bool:
    assert isinstance(ht, HammerPlaceAndRouteTool), "endcap insertion only for par"
    assert isinstance(ht, TCLTool), "endcap insertion can only run on TCL tools"
    endcap_cells=ht.technology.get_special_cell_by_type(CellType.EndCap)
    endcap_cell=endcap_cells[0].name[0]
    ht.append(
        f'''
set_db add_endcaps_boundary_tap     true
set_db add_endcaps_left_edge        {endcap_cell}
set_db add_endcaps_right_edge       {endcap_cell}
add_endcaps
    '''
    )
    return True

def calibre_drc_blackbox_srams(ht: HammerTool) -> bool:
    assert isinstance(ht, HammerDRCTool), "Exlude SRAMs only in DRC"
    drc_box = ''
    for name in SKY130Tech.sky130_sram_names():
        drc_box += f"\nEXCLUDE CELL {name}"
    run_file = ht.drc_run_file  # type: ignore
    with open(run_file, "a") as f:
        f.write(drc_box)
    return True

def pegasus_drc_blackbox_srams(ht: HammerTool) -> bool:
    assert isinstance(ht, HammerDRCTool), "Exlude SRAMs only in DRC"
    drc_box = ''
    for name in SKY130Tech.sky130_sram_names():
        drc_box += f"\nexclude_cell {name}"
    run_file = ht.drc_ctl_file  # type: ignore
    with open(run_file, "a") as f:
        f.write(drc_box)
    return True

def calibre_lvs_blackbox_srams(ht: HammerTool) -> bool:
    assert isinstance(ht, HammerLVSTool), "Blackbox and filter SRAMs only in LVS"
    lvs_box = ''
    for name in SKY130Tech.sky130_sram_names():
        lvs_box += f"\nLVS BOX {name}"
        lvs_box += f"\nLVS FILTER {name} OPEN "
    run_file = ht.lvs_run_file  # type: ignore
    with open(run_file, "a") as f:
        f.write(lvs_box)
    return True

def pegasus_lvs_blackbox_srams(ht: HammerTool) -> bool:
    assert isinstance(ht, HammerLVSTool), "Blackbox and filter SRAMs only in LVS"
    # A black box needs only the SRAM ports, so take them from the SRAM LEFs and do not
    # read sram22.spice: it is very large, and an install can .include files that are
    # not on this machine (sram22_sky130_macros_exp includes a /scratch path).
    port_file = os.path.join(ht.run_dir, "sram_blackbox_ports.spice")
    lef_macros = write_sram_port_subckts(sram_lef_files(ht), port_file)
    sram_names = list(dict.fromkeys(SKY130Tech.sky130_sram_names() + lef_macros))
    lvs_box = f'\nschematic_path "{port_file}" spice;'
    for name in sram_names:
        lvs_box += f"\nlvs_black_box -black {name}"
    run_file = ht.lvs_ctl_file  # type: ignore
    with open(run_file) as f:
        contents = f.read()
    # Remove SRAM SPICE file includes.
    pattern = 'schematic_path.*({}).*spice;\n'.format('|'.join(map(re.escape, sram_names + ["sram22.spice"])))
    with open(run_file, "w") as f:
        f.write(re.sub(pattern, "", contents) + lvs_box)
    return True

def sram_lef_files(ht: HammerTool) -> List[str]:
    """LEF files of the SRAM macros (libraries that provide lib_type sram)."""
    return ht.technology.read_libs(
        [filters.lef_filter], HammerTechnologyUtils.to_plain_item,
        extra_pre_filters=[lambda lib: any(p.lib_type == "sram" for p in (lib.provides or []))])

def write_sram_port_subckts(lef_files: List[str], out_file: str) -> List[str]:
    """Write one empty .SUBCKT per LEF macro, with its pins (bus bits as name[i]) as ports.
    Return the macro names."""
    macros = []
    with open(out_file, "w") as f:
        f.write("* SRAM ports for the LVS black boxes, from the SRAM LEFs.\n")
        for lef in lef_files:
            macro, pins = None, []
            with open(lef) as lf:
                for line in lf:
                    tok = line.split()
                    if len(tok) < 2:
                        continue
                    if tok[0] == "MACRO":
                        macro, pins = tok[1], []
                    elif tok[0] == "PIN" and macro:
                        pins.append(tok[1])
                    elif tok[0] == "END" and tok[1] == macro:
                        if macro not in macros:
                            macros.append(macro)
                            f.write(f"\n.SUBCKT {macro}\n")
                            for i in range(0, len(pins), 8):
                                f.write("+ " + " ".join(pins[i:i + 8]) + "\n")
                            f.write(".ENDS\n")
                        macro = None
    return macros

# The IO cells, the HVL cells and the PoR call sky130_fd_pr__* subckts: map them to the deck's
# devices (see the .cdl header). The map has no sram22 bitcell devices (special_nfet_latch/pass,
# special_pfet_*), so it supports SRAMs only as black boxes (technology.sky130.lvs_blackbox_srams).
def pegasus_lvs_add_130a_primitives(ht: HammerTool) -> bool:
    assert isinstance(ht, HammerLVSTool), "Add sky130A primitives only in LVS"
    device_map = os.path.join(os.path.dirname(__file__), "sky130_fd_pr_pegasus_lvs.cdl")
    hvl_spice = os.path.join(ht.get_setting("technology.sky130.sky130A"),
                             "libs.ref", "sky130_fd_sc_hvl", "spice", "sky130_fd_sc_hvl.spice")
    lvs_box = f'\nschematic_path "{device_map}" cdl;'
    lvs_box += f'\nschematic_path "{hvl_spice}" spice;'
    lvs_box += "\nlvs_filter_device R (*res_generic_po) -short -source;"
    lvs_box += "\nlvs_filter_device C (cap_mim_m3_2) -open -source;"
    # The metal resistors (res_generic_m1..m5, 0.01 um long) only split net names: short them on
    # both sides, as their schematic W/L have no unit.
    lvs_box += "\nlvs_filter_device R (*res_generic_m?) -short;"
    # this is because otherwise lvs crashes with tons of stdcell-level pin mismatches
    lvs_box += """\nlvs_inconsistent_reduction_threshold -none;"""
    run_file = ht.lvs_ctl_file  # type: ignore
    with open(run_file, "a") as f:
        f.write(lvs_box)
    return True

def sram22_lvs_recognize_gates_all(ht: HammerTool) -> bool:
    assert isinstance(ht, HammerLVSTool), "Change 'LVS RECOGNIZE GATES' from 'NONE' to 'ALL' for SRAM22"
    run_file = ht.lvs_run_file  # type: ignore
    with open(run_file, "a") as f:
        f.write("LVS RECOGNIZE GATES ALL")
    return True

# exclude sky130A IOs from pegasus for now
# in theory IO cells should be DRC clean or all DRCs should be waiveable.
def pegasus_drc_blackbox_io_cells(ht: HammerTool) -> bool:
    assert isinstance(ht, HammerDRCTool) and ht.tool_config_prefix() == "drc.pegasus", (
        "Exlude IOs only for Pegasus DRC"
    )
    drc_box = ""
    io_cell_names = [
        "sky130_ef_io__*"
    ]  
    for name in io_cell_names:
        drc_box += f"\nexclude_cell {name}"
    run_file = ht.drc_ctl_file  # type: ignore
    with open(run_file, "a") as f:
        f.write(drc_box)
    return True

# we need this because:
# * (while cadence std cell ports are on M1), IO cells (openPDKs) ports are still on LI1
# * we need to tell Innovus to see/be aware of the LI1 layer (since ports are on that layer), as opposed to abstracting it out (and only seeing met1 & above).
# * not adding li1 as masterslice => openPDK io cell ports not being seen; if it is not set to a masterslice, Innovus will use LI1 as a routing layer, which will cause congestion + problems when other [cadence] cells' ports are on Met1.
# * nwell & pwell are copied from sky130_fd_sc_hd__nom.tlef with the same argument

# licon changes Needed in order to enforce the layer ordering in Innovus, otherwise may get error such as 
# You need to have cut layer after layer 'pwell'.
# broadly this is a repeat of information from the stackup image
_additional_tlef_edit_for_scl = """
LAYER nwell
  TYPE MASTERSLICE ;
END nwell
LAYER pwell
  TYPE MASTERSLICE ;
END pwell
LAYER li1
  TYPE MASTERSLICE ;
END li1
LAYER AREAIDLD
  TYPE MASTERSLICE ;
END AREAIDLD
LAYER licon
  TYPE CUT ;
END licon
"""

LVS_DECK_INSERT_LINES = """
LVS FILTER D  OPEN  SOURCE
LVS FILTER D  OPEN  LAYOUT
"""

LVS_DECK_SCRUB_LINES = [
    "VIRTUAL CONNECT REPORT",
    "SOURCE PRIMARY",
    "SOURCE SYSTEM SPICE",
    "SOURCE PATH",
    "ERC",
    "LVS REPORT",
]

tech = SKY130Tech()
