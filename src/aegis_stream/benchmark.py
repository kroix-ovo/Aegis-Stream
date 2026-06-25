"""Software benchmark harness for parser, book, feature, model, and replay."""

from __future__ import annotations

import argparse
from dataclasses import asdict
import json
from pathlib import Path
from time import perf_counter_ns

from .book import MultiSymbolOrderBook
from .features import FeatureWindowEngine
from .itch import CanonicalEvent, demo_payload, parse_messages
from .model import FixedPointTemporalMixer
from .pipeline import csv_report, run_replay_capture, stress_payload
from .telemetry import summarize_latencies
from .transport import decode_transport


def benchmark_payload(
    payload: bytes,
    *,
    iterations: int = 3,
    window: int = 128,
    feature_count: int = 64,
) -> dict[str, object]:
    if iterations <= 0:
        raise ValueError("iterations must be positive")

    parser = benchmark_parser(payload, iterations=iterations)
    events = parse_messages(payload)
    book = benchmark_book(events, iterations=iterations)
    feature = benchmark_features(events, iterations=iterations, window=window, feature_count=feature_count)
    model = benchmark_model(feature["last_matrix"], iterations=max(iterations, len(events)), feature_count=feature_count)
    replay = run_replay_capture(payload, protocol="raw", window=window, feature_count=feature_count)
    return {
        "input_bytes": len(payload),
        "events": len(events),
        "parser": parser,
        "book": {key: value for key, value in book.items() if key != "snapshots"},
        "feature": {key: value for key, value in feature.items() if key != "last_matrix"},
        "model": model,
        "end_to_end": replay.to_jsonable(),
    }


def benchmark_parser(payload: bytes, *, iterations: int = 3) -> dict[str, object]:
    event_count = 0
    start = perf_counter_ns()
    for _ in range(iterations):
        events = parse_messages(payload)
        event_count = len(events)
    elapsed = perf_counter_ns() - start
    seconds = elapsed / 1_000_000_000
    total_events = event_count * iterations
    total_bytes = len(payload) * iterations
    return {
        "iterations": iterations,
        "events_per_iteration": event_count,
        "elapsed_ns": elapsed,
        "events_per_second": int(total_events / seconds) if seconds else 0,
        "bytes_per_second": int(total_bytes / seconds) if seconds else 0,
    }


def benchmark_book(events: list[CanonicalEvent], *, iterations: int = 3) -> dict[str, object]:
    timings: list[int] = []
    issues = 0
    snapshots = []
    for _ in range(iterations):
        book = MultiSymbolOrderBook(strict=True)
        for event in events:
            start = perf_counter_ns()
            snapshot = book.apply_event(event)
            timings.append(perf_counter_ns() - start)
            snapshots.append(snapshot)
        issues += len(book.issues)
    return {
        "events": len(events),
        "iterations": iterations,
        "issue_count": issues,
        "mismatch_count": 0,
        "latency_ns": summarize_latencies(timings),
        "snapshots": snapshots,
    }


def benchmark_features(
    events: list[CanonicalEvent],
    *,
    iterations: int = 3,
    window: int = 128,
    feature_count: int = 64,
) -> dict[str, object]:
    timings: list[int] = []
    last_matrix: list[list[int]] = [[0] * feature_count for _ in range(window)]
    for _ in range(iterations):
        book = MultiSymbolOrderBook(strict=True)
        engines: dict[str, FeatureWindowEngine] = {}
        for event in events:
            snapshot = book.apply_event(event)
            engine = engines.setdefault(snapshot.symbol, FeatureWindowEngine(window=window, feature_count=feature_count))
            start = perf_counter_ns()
            engine.update(event, snapshot)
            timings.append(perf_counter_ns() - start)
            last_matrix = engine.matrix()
    return {
        "events": len(events),
        "iterations": iterations,
        "latency_ns": summarize_latencies(timings),
        "last_matrix": last_matrix,
    }


def benchmark_model(
    window: list[list[int]],
    *,
    iterations: int = 32,
    feature_count: int = 64,
) -> dict[str, object]:
    timings: list[int] = []
    model = FixedPointTemporalMixer(feature_count=feature_count)
    result = None
    for _ in range(iterations):
        start = perf_counter_ns()
        result = model.predict(window)
        timings.append(perf_counter_ns() - start)
    return {
        "iterations": iterations,
        "latency_ns": summarize_latencies(timings),
        "last_inference": None if result is None else asdict(result),
    }


def benchmark_capture(
    data: bytes,
    *,
    protocol: str,
    packet_framing: str = "auto",
    pcap_inner: str = "moldudp64",
    iterations: int = 3,
    window: int = 128,
    feature_count: int = 64,
) -> dict[str, object]:
    transport = decode_transport(data, protocol=protocol, packet_framing=packet_framing, pcap_inner=pcap_inner)
    report = benchmark_payload(transport.payload, iterations=iterations, window=window, feature_count=feature_count)
    report["transport"] = transport.to_jsonable()["counters"]
    return report


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Benchmark Aegis-Stream software replay components.")
    parser.add_argument("--demo", action="store_true", help="benchmark the built-in deterministic trace")
    parser.add_argument("--stress", type=int, default=512, help="generated stress event count")
    parser.add_argument("--symbols", type=int, default=4, help="symbol count for generated stress input")
    parser.add_argument("--input", help="binary payload, transport capture, or pcap file")
    parser.add_argument("--format", choices=["raw", "moldudp64", "soupbintcp", "pcap"], default="raw")
    parser.add_argument("--packet-framing", choices=["auto", "none", "u16", "u32"], default="auto")
    parser.add_argument("--pcap-inner", choices=["raw", "moldudp64"], default="moldudp64")
    parser.add_argument("--iterations", type=int, default=3)
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--csv", action="store_true")
    parser.add_argument("--output")
    args = parser.parse_args(argv)

    if args.input:
        data = Path(args.input).read_bytes()
        report = benchmark_capture(
            data,
            protocol=args.format,
            packet_framing=args.packet_framing,
            pcap_inner=args.pcap_inner,
            iterations=args.iterations,
        )
    else:
        payload = demo_payload() if args.demo else stress_payload(events=args.stress, symbols=args.symbols)
        report = benchmark_payload(payload, iterations=args.iterations)

    if args.csv:
        rendered = csv_report(report)
    else:
        rendered = json.dumps(report, indent=2, sort_keys=True) + "\n"

    if args.output:
        Path(args.output).write_text(rendered)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
