# Aegis-Stream

Aegis-Stream is a research-grade FPGA systems project for deterministic
market-data ingest, limit-order-book analytics, and low-batch quantized sequence
inference. The repository turns the supplied architecture brief into a runnable
seed implementation:

- MoldUDP64, SoupBinTCP-style, raw payload, generated stress, and classic PCAP
  replay inputs for captured market-data payloads.
- A hardened Python golden path for Nasdaq TotalView-ITCH style event parsing.
- Stateful multi-symbol order-reference and top-of-book reconstruction.
- Streaming microstructure feature-window generation.
- Float and fixed-point int8 temporal-mixer reference models for
  hardware/software co-design.
- Stage-wise telemetry, replay, benchmark, and report tooling.
- SystemVerilog interface contracts, starter RTL, simulation-stage parser,
  transport, book, feature-window, and int8 mixer modules with cocotb
  scoreboards.

## Quick Start

```bash
PYTHONPATH=src python3 -m unittest discover -s tests
PYTHONPATH=src python3 -m aegis_stream.pipeline --demo --json
PYTHONPATH=src python3 -m aegis_stream.pipeline --stress 1024 --csv
PYTHONPATH=src python3 -m aegis_stream.benchmark --stress 1024 --json
```

## Repository Layout

```text
src/aegis_stream/      Python golden models and replay pipeline
tests/                 Unit tests for parser, book, feature, model, and replay
tools/                 Developer-facing replay helpers
hardware/rtl/          SystemVerilog package and starter modules
hardware/cocotb/       Icarus/cocotb scoreboards against Python references
docs/                  Architecture, interfaces, benchmarking, and roadmap
docs/source/           Original supplied research report and PDF
.github/workflows/    CI configuration for Python, Verilator, and cocotb gates
```

## Current Status

This is a software-complete golden-model and simulation-grade RTL repo, not a
completed FPGA implementation (I do not have money for a research grade FPGA).
The software path is executable and tested across parser, transport replay, 
multi-symbol book state, feature generation, fixed-point model inference, benchmark, and reporting flows. 
The RTL path now has Verilator lint/smoke coverage plus Icarus/cocotb scoreboards for aligned
canonicalization, cross-beat packet buffering, order-reference lifecycle,
transport sequence counters, telemetry packing, single-shard top-K price
levels, feature-window buffering, and a fixed-point int8 mixer MVP.

The main next big milestones I must complete are:

1. Compose the packet buffer and canonicalizer into a deeper streaming parser
   pipeline with randomized multi-message backpressure.
2. Expand the top-K price-level MVP into a canonical-event-driven book pipeline
   fed by the order-reference store.
3. Introduce HBM-bank simulation and then vendor HBM integration for the
   order-reference store.
4. Replace the int8 mixer MVP with the full exported temporal-mixer lookback
   datapath or Chisel-generated RTL.
5. Add XRT/QDMA replay and hardware telemetry extraction for board bring-up.

## Validation

The Python regression suite covers:

- ITCH message decoding and canonical 256-bit packing.
- Transport capture decoding, malformed capture accounting, and sequence-gap
  detection.
- Add, execute, cancel, delete, replace, and trade book-state behavior across
  strict/non-strict and multi-symbol paths.
- Feature-window generation, float/fixed model scoring, and fixed-point
  determinism checks.
- End-to-end replay output, benchmark summaries, and telemetry percentile
  schemas.

Run:

```bash
make test
make lint-rtl
make sim-rtl
make test-rtl-cocotb PYTHON=cocotb-env/bin/python SIM=icarus
make validate
make demo
```

`make lint-rtl` sets `LANG=C LC_ALL=C` because the Homebrew Verilator bottle can
panic in shells configured for `C.UTF-8`. `make sim-rtl` compiles and runs the
current Verilator smoke tests for the aligned ITCH canonicalizer and the
order-reference store.

`make test-rtl-cocotb` uses Icarus Verilog by default and runs cocotb
scoreboards. The local virtualenv `cocotb-env/` is intentionally ignored; install
the optional dependencies with `python -m pip install -e ".[dev]"` or point
`PYTHON` at any environment that has cocotb installed.

## Source Brief

The architecture reference artifacts are preserved under `docs/source/`:

- `Aegis-Stream.pdf`
- `deep-research-report.md`

Those files remain the architecture authority for target latency, hardware
platform assumptions, benchmarking methodology, and long-term deliverables.
