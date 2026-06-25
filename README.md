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
- SystemVerilog interface contracts and starter RTL for the canonical event
  path.

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
docs/                  Architecture, interfaces, benchmarking, and roadmap
docs/source/           Original supplied research report and PDF
.github/workflows/    CI configuration for the Python regression suite
```

## Current Status

This is a software-complete golden-model and starter-RTL repo, not a completed
FPGA implementation. The software path is executable and tested across parser,
transport replay, multi-symbol book state, feature generation, fixed-point model
inference, benchmark, and reporting flows. The RTL path defines stable data
contracts and starter modules that can be expanded into the full U55C/Agilex
board build described in the research brief.

The main next engineering milestones are:

1. Replace the aligned-message starter RTL canonicalizer with a packet-buffered
   variable-length ITCH parser.
2. Add cocotb scoreboards against `aegis_stream.itch`,
   `aegis_stream.transport`, and `aegis_stream.book`.
3. Introduce HBM-bank simulation and then vendor HBM integration for the
   order-reference store.
4. Port the feature engine and temporal mixer into Chisel or hand-written
   pipelined SystemVerilog.
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
make validate
make demo
```

`make lint-rtl` sets `LANG=C LC_ALL=C` because the Homebrew Verilator bottle can
panic in shells configured for `C.UTF-8`. `make sim-rtl` compiles and runs the
current Verilator smoke tests for the aligned ITCH canonicalizer and the
order-reference store.

## Source Brief

The architecture reference artifacts are preserved under `docs/source/`:

- `Aegis-Stream.pdf`
- `deep-research-report.md`

Those files remain the architecture authority for target latency, hardware
platform assumptions, benchmarking methodology, and long-term deliverables.
