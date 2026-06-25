# Hardware Tree

This directory contains the first hardware contracts for Aegis-Stream. The
files are intentionally narrow:

- `rtl/aegis_stream_pkg.sv` defines the canonical 256-bit event format.
- `rtl/itch_canonicalizer.sv` is a starter aligned-message canonicalizer for
  parser scoreboarding and early integration.
- `rtl/order_ref_store.sv` is a small synthesizable order-reference store for
  early lifecycle testing before the HBM-backed design lands.
- `rtl/latency_telemetry.sv` captures stage timestamps into a packed telemetry
  record.

Run static RTL checks with:

```bash
make lint-rtl
make sim-rtl
```

The Makefile pins `LANG=C LC_ALL=C` around Verilator so Homebrew's Perl runtime
does not inherit unsupported locale settings.

`make sim-rtl` currently builds and runs Verilator C++ smoke tests for the
aligned ITCH canonicalizer and the order-reference store.

The complete board implementation should grow around these contracts:

1. Add a transport decoder for Ethernet/IPv4/UDP plus sequence checking.
2. Replace the aligned canonicalizer with a buffered variable-length ITCH
   parser that supports cross-beat messages.
3. Add a banked order-reference store with an on-chip hot cache and HBM model.
4. Add the price-level engine, feature-window engine, and sequence core.
5. Introduce cocotb tests that reuse `src/aegis_stream` as the golden model.

The software package is the source of truth for functional scoreboarding until
the RTL path is mature.
