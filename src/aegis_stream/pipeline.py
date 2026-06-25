"""End-to-end software replay for Aegis-Stream."""

from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict, dataclass
import json
from pathlib import Path

from .book import BookIssue, BookSnapshot, MultiSymbolOrderBook, ReplayMismatch
from .features import FeatureWindowEngine
from .itch import (
    CanonicalEvent,
    ItchParseError,
    demo_payload,
    encode_add,
    encode_cancel,
    encode_delete,
    encode_execute,
    encode_replace,
    encode_trade,
    parse_messages,
)
from .model import FixedPointTemporalMixer, InferenceResult
from .telemetry import TelemetryRecorder
from .transport import TransportReplay, decode_raw_payload, decode_transport


@dataclass(frozen=True, slots=True)
class ReplayResult:
    events: list[CanonicalEvent]
    snapshots: list[BookSnapshot]
    vectors: list[list[int]]
    inferences: list[InferenceResult]
    telemetry_summary: dict[str, object]
    transport_summary: dict[str, object]
    parse_errors: list[str]
    book_issues: list[BookIssue]
    mismatches: list[ReplayMismatch]

    def to_jsonable(self) -> dict[str, object]:
        event_counts = Counter(event.event_type.value for event in self.events)
        return {
            "event_count": len(self.events),
            "event_type_counts": dict(sorted(event_counts.items())),
            "last_snapshot": asdict(self.snapshots[-1]) if self.snapshots else None,
            "last_vector": self.vectors[-1] if self.vectors else None,
            "last_inference": asdict(self.inferences[-1]) if self.inferences else None,
            "telemetry": self.telemetry_summary,
            "transport": self.transport_summary,
            "parse_error_count": len(self.parse_errors),
            "parse_errors": self.parse_errors,
            "book_issue_count": len(self.book_issues),
            "book_issues": [asdict(issue) for issue in self.book_issues],
            "book_mismatch_count": len(self.mismatches),
            "book_mismatches": [asdict(mismatch) for mismatch in self.mismatches],
        }


def run_replay(
    payload: bytes,
    *,
    symbol: str = "AEGIS",
    top_k: int = 32,
    window: int = 128,
    feature_count: int = 64,
    strict: bool = True,
) -> ReplayResult:
    transport = decode_raw_payload(payload)
    return _run_transport_replay(
        transport,
        symbol=symbol,
        top_k=top_k,
        window=window,
        feature_count=feature_count,
        strict=strict,
    )


def run_replay_capture(
    data: bytes,
    *,
    protocol: str = "raw",
    packet_framing: str = "auto",
    pcap_inner: str = "moldudp64",
    symbol: str = "AEGIS",
    top_k: int = 32,
    window: int = 128,
    feature_count: int = 64,
    strict: bool = True,
) -> ReplayResult:
    transport = decode_transport(
        data,
        protocol=protocol,
        packet_framing=packet_framing,  # type: ignore[arg-type]
        pcap_inner=pcap_inner,
    )
    return _run_transport_replay(
        transport,
        symbol=symbol,
        top_k=top_k,
        window=window,
        feature_count=feature_count,
        strict=strict,
    )


def _run_transport_replay(
    transport: TransportReplay,
    *,
    symbol: str,
    top_k: int,
    window: int,
    feature_count: int,
    strict: bool,
) -> ReplayResult:
    parse_start_ns = TelemetryRecorder.now_ns()
    events: list[CanonicalEvent] = []
    parse_errors: list[str] = []
    for packet in transport.packets:
        if not packet.payload:
            continue
        try:
            events.extend(parse_messages(packet.payload))
        except ItchParseError as exc:
            message = f"packet {packet.packet_index}: {exc}"
            parse_errors.append(message)
            if strict:
                raise
    parse_done_ns = TelemetryRecorder.now_ns()

    book = MultiSymbolOrderBook(top_k=top_k, strict=strict, default_symbol=symbol)
    features_by_symbol: dict[str, FeatureWindowEngine] = {}
    model = FixedPointTemporalMixer(feature_count=feature_count)
    telemetry = TelemetryRecorder()

    snapshots: list[BookSnapshot] = []
    vectors: list[list[int]] = []
    inferences: list[InferenceResult] = []

    for index, event in enumerate(events):
        book_start_ns = TelemetryRecorder.now_ns()
        snapshot = book.apply_event(event)
        book_done_ns = TelemetryRecorder.now_ns()
        features = features_by_symbol.setdefault(
            snapshot.symbol,
            FeatureWindowEngine(window=window, feature_count=feature_count),
        )
        feature_start_ns = TelemetryRecorder.now_ns()
        vector = features.update(event, snapshot)
        feature_done_ns = TelemetryRecorder.now_ns()
        model_start_ns = TelemetryRecorder.now_ns()
        inference = model.predict(features.matrix())
        model_done_ns = TelemetryRecorder.now_ns()

        snapshots.append(snapshot)
        vectors.append(vector)
        inferences.append(inference)
        telemetry.append(
            event_index=index,
            exchange_timestamp_ns=event.timestamp_ns,
            parser_start_ns=parse_start_ns if index == 0 else parse_done_ns,
            parser_done_ns=parse_done_ns,
            book_start_ns=book_start_ns,
            book_done_ns=book_done_ns,
            feature_start_ns=feature_start_ns,
            feature_done_ns=feature_done_ns,
            model_start_ns=model_start_ns,
            model_done_ns=model_done_ns,
        )

    return ReplayResult(
        events,
        snapshots,
        vectors,
        inferences,
        telemetry.summary(),
        transport.to_jsonable()["counters"],
        parse_errors,
        book.issues,
        [],
    )


def stress_payload(*, events: int = 256, symbols: int = 4) -> bytes:
    """Generate a deterministic valid ITCH stress trace."""

    if events <= 0:
        return b""
    if symbols <= 0:
        raise ValueError("symbols must be positive")
    live_orders: dict[str, list[tuple[int, int]]] = {f"SYM{i:04d}"[:8]: [] for i in range(symbols)}
    next_ref = 10_000
    payload = bytearray()
    for index in range(events):
        symbol = f"SYM{index % symbols:04d}"[:8]
        side = "B" if index % 2 == 0 else "S"
        price = 100_0000 + (index % 17) * 100 + (0 if side == "B" else 500)
        timestamp = 1_000 + index * 10
        bucket = live_orders[symbol]
        op = index % 7
        if not bucket or op in {0, 1}:
            shares = 100 + (index % 5) * 25
            payload.extend(
                encode_add(
                    order_ref=next_ref,
                    side=side,
                    shares=shares,
                    stock=symbol,
                    price=price,
                    timestamp_ns=timestamp,
                    stock_locate=(index % symbols) + 1,
                    tracking_number=index & 0xFFFF,
                )
            )
            bucket.append((next_ref, shares))
            next_ref += 1
        elif op == 2:
            order_ref, shares = bucket[0]
            dec = max(1, shares // 4)
            payload.extend(encode_cancel(order_ref=order_ref, shares=dec, timestamp_ns=timestamp))
            remaining = shares - dec
            if remaining:
                bucket[0] = (order_ref, remaining)
            else:
                bucket.pop(0)
        elif op == 3:
            order_ref, shares = bucket[0]
            dec = max(1, shares // 3)
            payload.extend(encode_execute(order_ref=order_ref, shares=dec, match_number=50_000 + index, timestamp_ns=timestamp))
            remaining = shares - dec
            if remaining:
                bucket[0] = (order_ref, remaining)
            else:
                bucket.pop(0)
        elif op == 4:
            order_ref, _shares = bucket.pop(0)
            new_shares = 125 + (index % 4) * 25
            payload.extend(
                encode_replace(
                    old_order_ref=order_ref,
                    new_order_ref=next_ref,
                    shares=new_shares,
                    price=price,
                    timestamp_ns=timestamp,
                )
            )
            bucket.append((next_ref, new_shares))
            next_ref += 1
        elif op == 5:
            order_ref, _shares = bucket.pop(0)
            payload.extend(encode_delete(order_ref=order_ref, timestamp_ns=timestamp))
        else:
            payload.extend(
                encode_trade(
                    order_ref=next_ref,
                    side=side,
                    shares=10 + (index % 10),
                    stock=symbol,
                    price=price,
                    match_number=60_000 + index,
                    timestamp_ns=timestamp,
                    stock_locate=(index % symbols) + 1,
                    tracking_number=index & 0xFFFF,
                )
            )
            next_ref += 1
    return bytes(payload)


def csv_report(summary: dict[str, object]) -> str:
    lines = ["metric,value"]
    for key, value in _flatten_summary(summary):
        if isinstance(value, (dict, list, tuple)):
            value = json.dumps(value, sort_keys=True)
        lines.append(f"{key},{value}")
    return "\n".join(lines) + "\n"


def _flatten_summary(data: dict[str, object], prefix: str = "") -> list[tuple[str, object]]:
    rows: list[tuple[str, object]] = []
    for key, value in data.items():
        full_key = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            rows.extend(_flatten_summary(value, full_key))
        else:
            rows.append((full_key, value))
    return rows


def _payload_from_args(args: argparse.Namespace) -> tuple[bytes, str]:
    if args.demo:
        return demo_payload(), "raw"
    if args.stress:
        return stress_payload(events=args.stress, symbols=args.symbols), "raw"
    if args.hex:
        return bytes.fromhex(args.hex), args.format
    if args.input:
        return Path(args.input).read_bytes(), args.format
    raise SystemExit("provide --demo, --stress, --hex, or --input")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay ITCH messages through the Aegis-Stream golden path.")
    parser.add_argument("--demo", action="store_true", help="run the built-in deterministic trace")
    parser.add_argument("--stress", type=int, help="run a generated deterministic stress trace with N events")
    parser.add_argument("--symbols", type=int, default=4, help="symbol count for --stress")
    parser.add_argument("--hex", help="hex encoded payload or capture")
    parser.add_argument("--input", help="binary payload, transport capture, or pcap file")
    parser.add_argument(
        "--format",
        choices=["raw", "moldudp64", "soupbintcp", "pcap"],
        default="raw",
        help="input framing format",
    )
    parser.add_argument(
        "--packet-framing",
        choices=["auto", "none", "u16", "u32"],
        default="auto",
        help="MoldUDP64 datagram framing for binary captures",
    )
    parser.add_argument(
        "--pcap-inner",
        choices=["raw", "moldudp64"],
        default="moldudp64",
        help="UDP payload format inside classic pcap captures",
    )
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON summary")
    parser.add_argument("--csv", action="store_true", help="emit CSV summary")
    parser.add_argument("--output", help="write report to a file instead of stdout")
    parser.add_argument("--non-strict", action="store_true", help="record parse/book issues instead of stopping")
    args = parser.parse_args(argv)

    data, protocol = _payload_from_args(args)
    result = run_replay_capture(
        data,
        protocol=protocol,
        packet_framing=args.packet_framing,
        pcap_inner=args.pcap_inner,
        strict=not args.non_strict,
    )
    summary = result.to_jsonable()
    if args.csv:
        rendered = csv_report(summary)
    elif args.json:
        rendered = json.dumps(summary, indent=2, sort_keys=True) + "\n"
    else:
        last = result.inferences[-1] if result.inferences else None
        rendered = f"events={len(result.events)} telemetry={result.telemetry_summary}\n"
        if last:
            rendered += f"last_score_bps={last.score_bps} confidence={last.confidence} action={last.action}\n"
        if result.parse_errors or result.book_issues or result.mismatches:
            rendered += (
                f"parse_errors={len(result.parse_errors)} "
                f"book_issues={len(result.book_issues)} "
                f"book_mismatches={len(result.mismatches)}\n"
            )

    if args.output:
        Path(args.output).write_text(rendered)
    else:
        print(rendered, end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
