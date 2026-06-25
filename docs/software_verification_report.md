# Software Verification Report

This report summarizes the public software/golden-model implementation. It is
not a hardware timing claim; Python timings exist only to validate report schema
and replay instrumentation before FPGA telemetry is available.

## Correctness Scope

- ITCH parser supports add, attributed add, execute, execute-with-price, cancel,
  delete, replace, and non-cross trade messages with explicit truncated,
  unsupported, and validation error types.
- Replay accepts raw ITCH payloads, MoldUDP64 datagrams, SoupBinTCP-style frames,
  generated stress traces, and classic PCAP UDP captures where payloads can be
  extracted without external packet libraries.
- Transport counters report sequenced payloads, gaps, duplicate/replayed
  sequence ranges, malformed packets, malformed messages, control frames, and
  decoded payload bytes.
- The book model supports strict and non-strict modes, multi-symbol sharding,
  order-reference lifecycle checks, invariant checks, top-K depth signatures,
  and replay mismatch records.
- The model path includes a float inference scaffold, fixed-point int8
  inference, a deterministic exported weight fixture, and a dependency-free
  float baseline trainer/evaluator.
- RTL simulation includes Verilator lint/smoke tests plus cocotb scoreboards for
  parser canonicalization, cross-beat buffering, order-reference lifecycle,
  transport sequence counters, latency telemetry packing, top-K price levels,
  feature-window buffering, and an int8 mixer MVP.

## Metrics Schema

Replay and benchmark reports include:

- Event count and event-type distribution.
- Transport packet, payload, gap, duplicate, malformed, and byte counters.
- Parser throughput in events/sec and bytes/sec for software benchmark runs.
- Book issue count and replay mismatch count.
- Feature generation latency percentiles: median, p95, p99, max.
- Model inference latency percentiles: median, p95, p99, max.
- End-to-end replay telemetry with parser, book, feature, model, and aggregate
  software latency percentile buckets.

Regenerate a local snapshot with:

```bash
PYTHONPATH=src python3 tools/generate_report.py
```

## Remaining FPGA-Specific Work

- Actual FPGA board implementation, vendor shell bring-up, timing closure, and
  floorplanning.
- U55C/Agilex deployment, XRT/QDMA integration, CMAC/vendor shell integration,
  and hardware telemetry extraction.
- Production parser composition, banked/HBM order-reference store, full
  canonical-event-driven price-level pipeline, full temporal lookback model RTL,
  and board-calibrated telemetry.
