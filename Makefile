PYTHON ?= python3
VERILATOR ?= verilator
VERILATOR_ENV ?= LANG=C LC_ALL=C
VERILATOR_CFLAGS ?= -std=c++17 -Wno-unknown-warning-option
RTL_PKG := hardware/rtl/aegis_stream_pkg.sv
RTL_CANON := hardware/rtl/itch_canonicalizer.sv
RTL_TELEM := hardware/rtl/latency_telemetry.sv
RTL_ORDER := hardware/rtl/order_ref_store.sv
CANON_SMOKE := hardware/sim/itch_canonicalizer_smoke.cpp
ORDER_SMOKE := hardware/sim/order_ref_store_smoke.cpp

.PHONY: test test-python validate demo compile lint-rtl lint-rtl-canonicalizer lint-rtl-telemetry lint-rtl-order-store sim-rtl sim-rtl-canonicalizer sim-rtl-order-store clean

test: test-python

test-python:
	PYTHONPATH=src $(PYTHON) -m unittest discover -s tests

validate: test-python lint-rtl sim-rtl

demo:
	PYTHONPATH=src $(PYTHON) -m aegis_stream.pipeline --demo --json

compile:
	$(PYTHON) -m compileall src tests tools

lint-rtl: lint-rtl-canonicalizer lint-rtl-telemetry lint-rtl-order-store

lint-rtl-canonicalizer:
	$(VERILATOR_ENV) $(VERILATOR) --lint-only -Wall --sv --top-module itch_canonicalizer $(RTL_PKG) $(RTL_CANON)

lint-rtl-telemetry:
	$(VERILATOR_ENV) $(VERILATOR) --lint-only -Wall --sv --top-module latency_telemetry $(RTL_PKG) $(RTL_TELEM)

lint-rtl-order-store:
	$(VERILATOR_ENV) $(VERILATOR) --lint-only -Wall --sv --top-module order_ref_store $(RTL_PKG) $(RTL_ORDER)

sim-rtl: sim-rtl-canonicalizer sim-rtl-order-store

sim-rtl-canonicalizer:
	$(VERILATOR_ENV) $(VERILATOR) -Wall --sv --cc --exe --build -CFLAGS "$(VERILATOR_CFLAGS)" --top-module itch_canonicalizer $(RTL_PKG) $(RTL_CANON) $(CANON_SMOKE)
	./obj_dir/Vitch_canonicalizer

sim-rtl-order-store:
	$(VERILATOR_ENV) $(VERILATOR) -Wall --sv --cc --exe --build -CFLAGS "$(VERILATOR_CFLAGS)" --top-module order_ref_store $(RTL_PKG) $(RTL_ORDER) $(ORDER_SMOKE)
	./obj_dir/Vorder_ref_store

clean:
	rm -rf .pytest_cache .mypy_cache htmlcov build dist *.egg-info
	find . -type d -name __pycache__ -prune -exec rm -rf {} +
	rm -rf obj_dir
