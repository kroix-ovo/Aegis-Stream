"""End-to-end software replay for Aegis-Stream."""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path

from .book import BookSnapshot, OrderBookShard
from .features import FeatureWindowEngine
from .itch import CanonicalEvent, demo_payload, parse_messages
from .model import InferenceResult, QuantizedTemporalMixer
from .telemetry import TelemetryRecorder


@dataclass(frozen=True, slots=True)
class ReplayResult:
    events: list[CanonicalEvent]
    snapshots: list[BookSnapshot]
    vectors: list[list[int]]
    inferences: list[InferenceResult]
    telemetry_summary: dict[str, int | float]

    def to_jsonable(self) -> dict[str, object]:
        return {
            "event_count": len(self.events),
            "last_snapshot": asdict(self.snapshots[-1]) if self.snapshots else None,
            "last_vector": self.vectors[-1] if self.vectors else None,
            "last_inference": asdict(self.inferences[-1]) if self.inferences else None,
            "telemetry": self.telemetry_summary,
        }


def run_replay(
    payload: bytes,
    *,
    symbol: str = "AEGIS",
    top_k: int = 32,
    window: int = 128,
    feature_count: int = 64,
) -> ReplayResult:
    parser_done_ns = TelemetryRecorder.now_ns()
    events = parse_messages(payload)
    book = OrderBookShard(symbol=symbol, top_k=top_k)
    features = FeatureWindowEngine(window=window, feature_count=feature_count)
    model = QuantizedTemporalMixer(feature_count=feature_count)
    telemetry = TelemetryRecorder()

    snapshots: list[BookSnapshot] = []
    vectors: list[list[int]] = []
    inferences: list[InferenceResult] = []

    for index, event in enumerate(events):
        snapshot = book.apply_event(event)
        book_done_ns = TelemetryRecorder.now_ns()
        vector = features.update(event, snapshot)
        feature_done_ns = TelemetryRecorder.now_ns()
        inference = model.predict(features.matrix())
        model_done_ns = TelemetryRecorder.now_ns()

        snapshots.append(snapshot)
        vectors.append(vector)
        inferences.append(inference)
        telemetry.append(
            event_index=index,
            exchange_timestamp_ns=event.timestamp_ns,
            parser_done_ns=parser_done_ns,
            book_done_ns=book_done_ns,
            feature_done_ns=feature_done_ns,
            model_done_ns=model_done_ns,
        )
        parser_done_ns = TelemetryRecorder.now_ns()

    return ReplayResult(events, snapshots, vectors, inferences, telemetry.summary())


def _payload_from_args(args: argparse.Namespace) -> bytes:
    if args.demo:
        return demo_payload()
    if args.hex:
        return bytes.fromhex(args.hex)
    if args.input:
        return Path(args.input).read_bytes()
    raise SystemExit("provide --demo, --hex, or --input")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay ITCH messages through the Aegis-Stream golden path.")
    parser.add_argument("--demo", action="store_true", help="run the built-in deterministic trace")
    parser.add_argument("--hex", help="hex encoded concatenated ITCH payload")
    parser.add_argument("--input", help="binary payload file")
    parser.add_argument("--json", action="store_true", help="emit machine-readable summary")
    args = parser.parse_args(argv)

    result = run_replay(_payload_from_args(args))
    if args.json:
        print(json.dumps(result.to_jsonable(), indent=2, sort_keys=True))
    else:
        last = result.inferences[-1] if result.inferences else None
        print(f"events={len(result.events)} telemetry={result.telemetry_summary}")
        if last:
            print(f"last_score_bps={last.score_bps} confidence={last.confidence} action={last.action}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
