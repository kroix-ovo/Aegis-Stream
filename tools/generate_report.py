#!/usr/bin/env python3
"""Generate the software verification report for Aegis-Stream."""

from __future__ import annotations

from pathlib import Path

from aegis_stream.benchmark import benchmark_payload
from aegis_stream.pipeline import stress_payload


def render_report() -> str:
    report = benchmark_payload(stress_payload(events=128, symbols=4), iterations=1, window=32)
    parser = report["parser"]
    book = report["book"]
    feature = report["feature"]
    model = report["model"]
    return f"""# Software Verification Report

This report summarizes the public software/golden-model implementation. It is
generated from deterministic synthetic replay data and is not a hardware timing
claim.

## Correctness Scope

- ITCH parser supports add, attributed add, execute, execute-with-price, cancel,
  delete, replace, and non-cross trade messages.
- MoldUDP64, SoupBinTCP-style framed streams, raw payloads, and classic PCAP UDP
  captures can feed the replay path.
- The book model supports strict and non-strict modes, multi-symbol sharding,
  order-reference lifecycle checks, and top-K depth mismatch reporting.
- The model path includes float inference, fixed-point int8 inference, a
  deterministic exported weight fixture, and a dependency-free float baseline
  trainer/evaluator.

## Deterministic Benchmark Snapshot

| Metric | Value |
|---|---:|
| Events | {report["events"]} |
| Parser events/sec | {parser["events_per_second"]} |
| Book mismatch count | {book["mismatch_count"]} |
| Book issue count | {book["issue_count"]} |
| Feature median ns | {feature["latency_ns"]["median_ns"]} |
| Model median ns | {model["latency_ns"]["median_ns"]} |

## Remaining FPGA-Specific Work

- Actual FPGA board implementation, vendor shell bring-up, and timing closure.
- U55C/Agilex deployment, XRT/QDMA integration, and hardware telemetry capture.
- Variable-length RTL parser, banked/HBM order store, feature RTL, and sequence
  compute RTL beyond the starter smoke-tested modules.
"""


def main() -> int:
    output = Path("docs/software_verification_report.md")
    output.write_text(render_report())
    print(output)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
