# Benchmarking Methodology

The project separates correctness, model quality, and systems performance.

## Correctness

Required checks:

- Parser fields match the ITCH golden model byte-for-byte.
- The order-reference lifecycle is exact for add, execute, cancel, delete, and
  replace.
- Top-K bid and ask levels match the software book after every event.
- Feature vectors match the bit-true software implementation.
- Model outputs match the fixed-point software model for a frozen weight set.

## Systems Metrics

The hardware target from the research brief is:

| Stage | Primary target |
|---|---:|
| Parser plus canonicalization | under 250 ns median |
| Book plus feature update | under 400 ns median |
| Model latency | under 800 ns median |
| End-to-end tick to score | under 1.5 us median, under 2.0 us p99 |
| AI microbenchmark | over 250 GOPS on U55C |

The current Python telemetry is not a hardware performance proxy. It exists so
that the data schema and reporting flow are already in place before the RTL path
is connected.

## Reporting Format

For each run, report:

- Dataset or replay source.
- Message count and event-type distribution.
- Median, p95, p99, and max stage latencies.
- Book mismatch count.
- Feature/model mismatch count.
- Drops, gaps, malformed-packet count, and backpressure events.
- Device resource utilization and timing summary when hardware is available.

## Software Tools

The current repository includes dependency-light software benchmark and replay
tools. These timings validate schemas and catch regressions; they are not FPGA
latency proxies.

```bash
PYTHONPATH=src python3 -m aegis_stream.pipeline --demo --json
PYTHONPATH=src python3 -m aegis_stream.pipeline --stress 10000 --csv
PYTHONPATH=src python3 -m aegis_stream.pipeline --input capture.bin --format moldudp64 --json
PYTHONPATH=src python3 -m aegis_stream.pipeline --input capture.pcap --format pcap --pcap-inner moldudp64 --json
PYTHONPATH=src python3 -m aegis_stream.benchmark --stress 10000 --iterations 3 --json
```

`aegis_stream.benchmark` reports parser throughput, book issue and mismatch
counts, feature-generation latency percentiles, model-inference latency
percentiles, and the end-to-end replay summary. `tools/generate_report.py`
renders `docs/software_verification_report.md` from a deterministic stress
trace for local snapshots.

## Baselines

Recommended comparison classes:

- Software LOB model baseline on FI-2010 or comparable reconstructed data.
- hls4ml or FINN low-latency FPGA inference baseline.
- Attention-kernel baseline in the U55C class for AI microbenchmarks.
- Aegis-Stream end-to-end replay with stage-wise telemetry.
