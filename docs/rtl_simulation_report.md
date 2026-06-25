# RTL Simulation Report

This report describes the non-FPGA RTL simulation stack. It is not a timing,
placement, shell, DMA, or board-integration claim.

## Implemented Modules

- `itch_packet_buffer`: reassembles cross-beat ITCH payload bytes and emits one
  aligned message at a time.
- `itch_canonicalizer`: converts aligned ITCH A/F/E/C/X/D/U/P messages into the
  canonical 256-bit event contract.
- `transport_seq_checker`: tracks MoldUDP64-style packet sequence, gap,
  duplicate/replay, malformed, packet, and message counters.
- `order_ref_store`: validates insert, execute, cancel, delete, and replace
  lifecycle behavior.
- `price_level_topk`: maintains a small single-shard aggregate top-K bid/ask
  level view.
- `feature_window_buffer`: stores recent 64-int8 feature vectors in a ring.
- `temporal_mixer_int8`: computes a signed int8 dot-product score MVP.
- `latency_telemetry`: packs stage timestamps into the telemetry record.

## Local Gates

```bash
make validate PYTHON=python3 VERILATOR=verilator
make test-rtl-cocotb PYTHON=cocotb-env/bin/python SIM=icarus
```

`make validate` remains the core Python plus Verilator lint/smoke gate.
`make test-rtl-cocotb` is the simulation-scoreboard gate and uses Icarus by
default.

## Remaining FPGA-Only Work

- Vendor Ethernet/CMAC, PCIe, QDMA, XRT, HBM, and shell integration.
- U55C/Agilex deployment, constraints, timing closure, and floorplanning.
- Production-scale parser/book/model pipelines and board telemetry extraction.
