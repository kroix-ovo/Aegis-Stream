PYTHON ?= python3
VERILATOR ?= verilator
SIM ?= icarus
VERILATOR_ENV ?= LANG=C LC_ALL=C
VERILATOR_CFLAGS ?= -std=c++17 -Wno-unknown-warning-option
RTL_PKG := hardware/rtl/aegis_stream_pkg.sv
RTL_CANON := hardware/rtl/itch_canonicalizer.sv
RTL_TELEM := hardware/rtl/latency_telemetry.sv
RTL_ORDER := hardware/rtl/order_ref_store.sv
RTL_TRANSPORT := hardware/rtl/transport_seq_checker.sv
RTL_PACKET_BUFFER := hardware/rtl/itch_packet_buffer.sv
RTL_PRICE_LEVEL := hardware/rtl/price_level_topk.sv
RTL_FEATURE_WINDOW := hardware/rtl/feature_window_buffer.sv
RTL_MIXER := hardware/rtl/temporal_mixer_int8.sv
COCOTB_RUNNER := hardware/cocotb/run_cocotb.py
CANON_SMOKE := hardware/sim/itch_canonicalizer_smoke.cpp
ORDER_SMOKE := hardware/sim/order_ref_store_smoke.cpp

.PHONY: test test-python validate demo compile lint-rtl lint-rtl-canonicalizer lint-rtl-telemetry lint-rtl-order-store lint-rtl-transport lint-rtl-packet-buffer lint-rtl-price-level lint-rtl-feature-window lint-rtl-mixer sim-rtl sim-rtl-canonicalizer sim-rtl-order-store test-rtl-cocotb test-rtl-cocotb-parser test-rtl-cocotb-order test-rtl-cocotb-telemetry test-rtl-cocotb-transport test-rtl-cocotb-packet-buffer test-rtl-cocotb-price-level test-rtl-cocotb-feature-window test-rtl-cocotb-mixer test-rtl-cocotb-waves clean

test: test-python

test-python:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests

validate: test-python lint-rtl sim-rtl

demo:
	PYTHONPATH=src $(PYTHON) -m aegis_stream.pipeline --demo --json

compile:
	$(PYTHON) -m compileall src tests tools hardware/cocotb

lint-rtl: lint-rtl-canonicalizer lint-rtl-telemetry lint-rtl-order-store lint-rtl-transport lint-rtl-packet-buffer lint-rtl-price-level lint-rtl-feature-window lint-rtl-mixer

lint-rtl-canonicalizer:
	$(VERILATOR_ENV) $(VERILATOR) --lint-only -Wall --sv --top-module itch_canonicalizer $(RTL_PKG) $(RTL_CANON)

lint-rtl-telemetry:
	$(VERILATOR_ENV) $(VERILATOR) --lint-only -Wall --sv --top-module latency_telemetry $(RTL_PKG) $(RTL_TELEM)

lint-rtl-order-store:
	$(VERILATOR_ENV) $(VERILATOR) --lint-only -Wall --sv --top-module order_ref_store $(RTL_PKG) $(RTL_ORDER)

lint-rtl-transport:
	$(VERILATOR_ENV) $(VERILATOR) --lint-only -Wall --sv --top-module transport_seq_checker $(RTL_TRANSPORT)

lint-rtl-packet-buffer:
	$(VERILATOR_ENV) $(VERILATOR) --lint-only -Wall --sv --top-module itch_packet_buffer $(RTL_PACKET_BUFFER)

lint-rtl-price-level:
	$(VERILATOR_ENV) $(VERILATOR) --lint-only -Wall --sv --top-module price_level_topk $(RTL_PRICE_LEVEL)

lint-rtl-feature-window:
	$(VERILATOR_ENV) $(VERILATOR) --lint-only -Wall --sv --top-module feature_window_buffer $(RTL_FEATURE_WINDOW)

lint-rtl-mixer:
	$(VERILATOR_ENV) $(VERILATOR) --lint-only -Wall --sv --top-module temporal_mixer_int8 $(RTL_MIXER)

sim-rtl: sim-rtl-canonicalizer sim-rtl-order-store

sim-rtl-canonicalizer:
	$(VERILATOR_ENV) $(VERILATOR) -Wall --sv --cc --exe --build -CFLAGS "$(VERILATOR_CFLAGS)" --top-module itch_canonicalizer $(RTL_PKG) $(RTL_CANON) $(CANON_SMOKE)
	./obj_dir/Vitch_canonicalizer

sim-rtl-order-store:
	$(VERILATOR_ENV) $(VERILATOR) -Wall --sv --cc --exe --build -CFLAGS "$(VERILATOR_CFLAGS)" --top-module order_ref_store $(RTL_PKG) $(RTL_ORDER) $(ORDER_SMOKE)
	./obj_dir/Vorder_ref_store

test-rtl-cocotb: test-rtl-cocotb-parser test-rtl-cocotb-order test-rtl-cocotb-telemetry test-rtl-cocotb-transport test-rtl-cocotb-packet-buffer test-rtl-cocotb-price-level test-rtl-cocotb-feature-window test-rtl-cocotb-mixer

test-rtl-cocotb-parser:
	PYTHONPATH=src SIM=$(SIM) $(PYTHON) $(COCOTB_RUNNER) parser

test-rtl-cocotb-order:
	PYTHONPATH=src SIM=$(SIM) $(PYTHON) $(COCOTB_RUNNER) order

test-rtl-cocotb-telemetry:
	PYTHONPATH=src SIM=$(SIM) $(PYTHON) $(COCOTB_RUNNER) telemetry

test-rtl-cocotb-transport:
	PYTHONPATH=src SIM=$(SIM) $(PYTHON) $(COCOTB_RUNNER) transport

test-rtl-cocotb-packet-buffer:
	PYTHONPATH=src SIM=$(SIM) $(PYTHON) $(COCOTB_RUNNER) packet-buffer

test-rtl-cocotb-price-level:
	PYTHONPATH=src SIM=$(SIM) $(PYTHON) $(COCOTB_RUNNER) price-level

test-rtl-cocotb-feature-window:
	PYTHONPATH=src SIM=$(SIM) $(PYTHON) $(COCOTB_RUNNER) feature-window

test-rtl-cocotb-mixer:
	PYTHONPATH=src SIM=$(SIM) $(PYTHON) $(COCOTB_RUNNER) mixer

test-rtl-cocotb-waves:
	PYTHONPATH=src SIM=$(SIM) WAVES=1 $(PYTHON) $(COCOTB_RUNNER) all

clean:
	rm -rf .pytest_cache .mypy_cache htmlcov build dist *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf obj_dir sim_build results.xml
