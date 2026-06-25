"""Deterministic int8 temporal-mixer inference model.

This is a compact software stand-in for the hardware sequence core. It is not a
trained financial model; it provides a deterministic, bit-stable inference path
for integration tests, feature validation, and future RTL scoreboarding.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from .features import clamp_i8


@dataclass(frozen=True, slots=True)
class InferenceResult:
    score_bps: int
    confidence: int
    action: str
    raw_logit: int


class QuantizedTemporalMixer:
    """Small int8/int32 sparse temporal mixer with deterministic weights."""

    def __init__(self, *, feature_count: int = 64, hidden: int = 16, lookback: int = 32) -> None:
        if feature_count <= 0 or hidden <= 0 or lookback <= 0:
            raise ValueError("feature_count, hidden, and lookback must be positive")
        self.feature_count = feature_count
        self.hidden = hidden
        self.lookback = lookback
        self.input_weights = [
            [self._weight(h, f) for f in range(feature_count)] for h in range(hidden)
        ]
        self.output_weights = [self._weight(31, h) for h in range(hidden)]
        self.bias = [((h * 17 + 5) % 31) - 15 for h in range(hidden)]

    def predict(self, window: Sequence[Sequence[int]]) -> InferenceResult:
        rows = list(window)[-self.lookback :]
        if not rows:
            rows = [[0] * self.feature_count]

        hidden_values: list[int] = []
        for h in range(self.hidden):
            acc = self.bias[h] << 8
            for age, row in enumerate(rows):
                recency = age + 1
                for f, value in enumerate(row[: self.feature_count]):
                    if ((f + h + age) & 0x3) == 0:
                        acc += int(value) * self.input_weights[h][f] * recency
            hidden_values.append(clamp_i8(acc >> 10))

        raw_logit = 0
        for h, value in enumerate(hidden_values):
            raw_logit += value * self.output_weights[h]

        score_bps = max(-500, min(500, raw_logit // 8))
        confidence = min(100, abs(score_bps) // 5)
        if score_bps > 10:
            action = "BUY"
        elif score_bps < -10:
            action = "SELL"
        else:
            action = "HOLD"
        return InferenceResult(score_bps, confidence, action, raw_logit)

    @staticmethod
    def _weight(row: int, col: int) -> int:
        # Deterministic pseudo-random int4-like coefficient in [-7, 7].
        value = (row * 37 + col * 19 + row * col * 3 + 11) % 15
        return value - 7
