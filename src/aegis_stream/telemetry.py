"""Stage-wise replay telemetry."""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from statistics import median
from time import perf_counter_ns


@dataclass(frozen=True, slots=True)
class StageTelemetry:
    event_index: int
    exchange_timestamp_ns: int
    parser_done_ns: int
    book_done_ns: int
    feature_done_ns: int
    model_done_ns: int

    @property
    def software_latency_ns(self) -> int:
        return self.model_done_ns - self.parser_done_ns


class TelemetryRecorder:
    def __init__(self) -> None:
        self.records: list[StageTelemetry] = []

    @staticmethod
    def now_ns() -> int:
        return perf_counter_ns()

    def append(
        self,
        *,
        event_index: int,
        exchange_timestamp_ns: int,
        parser_done_ns: int,
        book_done_ns: int,
        feature_done_ns: int,
        model_done_ns: int,
    ) -> None:
        self.records.append(
            StageTelemetry(
                event_index,
                exchange_timestamp_ns,
                parser_done_ns,
                book_done_ns,
                feature_done_ns,
                model_done_ns,
            )
        )

    def summary(self) -> dict[str, int | float]:
        latencies = [record.software_latency_ns for record in self.records]
        if not latencies:
            return {"events": 0, "median_ns": 0, "p95_ns": 0, "p99_ns": 0, "max_ns": 0}
        ordered = sorted(latencies)
        return {
            "events": len(latencies),
            "median_ns": int(median(ordered)),
            "p95_ns": percentile(ordered, 95),
            "p99_ns": percentile(ordered, 99),
            "max_ns": ordered[-1],
        }

    def json_lines(self) -> str:
        return "\n".join(json.dumps(asdict(record), sort_keys=True) for record in self.records)


def percentile(sorted_values: list[int], pct: int) -> int:
    if not sorted_values:
        return 0
    if pct <= 0:
        return sorted_values[0]
    if pct >= 100:
        return sorted_values[-1]
    idx = (len(sorted_values) - 1) * pct // 100
    return sorted_values[idx]
