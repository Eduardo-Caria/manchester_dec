SIM ?= icarus
TOPLEVEL_LANG = verilog
COCOTB_TOPLEVEL = tb
COCOTB_TEST_MODULES = test_rx
SIM_BUILD = sim_build/gl

WOKWI_ID := $(shell awk '$$1 == "wokwi_id:" { print $$2; exit }' ../info.yaml)
DUT_MODULE ?= tt_um_wokwi_$(WOKWI_ID)
PDK_LIBRARY := $(PDK_ROOT)/sky130A/libs.ref/sky130_fd_sc_hd/verilog

COMPILE_ARGS += -DDUT_MODULE=$(DUT_MODULE) -DGL_TEST -DFUNCTIONAL -DUSE_POWER_PINS -DSIM -DUNIT_DELAY=\#1
VERILOG_SOURCES += $(PDK_LIBRARY)/primitives.v
VERILOG_SOURCES += $(PDK_LIBRARY)/sky130_fd_sc_hd.v
VERILOG_SOURCES += $(CURDIR)/gate_level_netlist.v
VERILOG_SOURCES += $(CURDIR)/tb.v

include $(shell cocotb-config --makefiles)/Makefile.sim
