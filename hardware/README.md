# Hardware Tree

This directory contains the first hardware contracts for Aegis-Stream. The
files are intentionally narrow:

- `rtl/aegis_stream_pkg.sv` defines the canonical 256-bit event format.
- `rtl/itch_canonicalizer.sv` is a starter aligned-message canonicalizer for
  parser scoreboarding and early integration.
- `rtl/itch_packet_buffer.sv` buffers byte-valid stream beats and emits aligned
  ITCH messages, including cross-beat records.
- `rtl/transport_seq_checker.sv` tracks MoldUDP64-style sequence metadata,
  malformed packets, gaps, duplicate/replay packets, and expected sequence.
- `rtl/order_ref_store.sv` is a small synthesizable order-reference store for
  early lifecycle testing before the HBM-backed design lands.
- `rtl/price_level_topk.sv` is a single-shard top-K price-level simulation MVP.
- `rtl/feature_window_buffer.sv` stores recent 64-int8 feature vectors in a
  ring buffer.
- `rtl/temporal_mixer_int8.sv` is a fixed-point int8 dot-product mixer MVP for
  early datapath tests.
- `rtl/latency_telemetry.sv` captures stage timestamps into a packed telemetry
  record.

Run static RTL checks with:

```bash
make lint-rtl
make sim-rtl
make test-rtl-cocotb PYTHON=cocotb-env/bin/python SIM=icarus
```

The Makefile pins `LANG=C LC_ALL=C` around Verilator so Homebrew's Perl runtime
does not inherit unsupported locale settings.

`make sim-rtl` currently builds and runs Verilator C++ smoke tests for the
aligned ITCH canonicalizer and the order-reference store.

Cocotb/Icarus tests live under `hardware/cocotb/` and compare RTL behavior
against the Python package where practical. The SVA assertions remain enabled
for Verilator; the cocotb runner disables them for Icarus, which does not parse
the same assertion syntax.

The complete board implementation should grow around these contracts:

1. Compose packet buffering, transport framing, and canonicalization into a
   deeper parser pipeline.
2. Add a banked order-reference store with an on-chip hot cache and HBM model.
3. Expand the top-K price-level MVP into a canonical-event-driven book engine.
4. Replace the feature/mixer MVPs with the full lookback sequence core.
5. Integrate board shell, DMA, timestamping, and hardware telemetry extraction.

The software package is the source of truth for functional scoreboarding until
the RTL path is mature.
