"""Float and fixed-point temporal-mixer reference models.

The fixed-point path is the bit-stable inference reference used by replay and
future RTL scoreboards. The float path and training helpers are intentionally
small scaffolds: they make the model workflow executable without committing the
public repo to a large external dataset or a heavyweight training dependency.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from typing import Sequence

from .features import clamp_i8


DEFAULT_WEIGHTS_PATH = Path(__file__).with_name("data") / "temporal_mixer_weights.json"


@dataclass(frozen=True, slots=True)
class InferenceResult:
    score_bps: int
    confidence: int
    action: str
    raw_logit: int


@dataclass(frozen=True, slots=True)
class FloatInferenceResult:
    score_bps: float
    confidence: float
    action: str
    raw_logit: float


@dataclass(frozen=True, slots=True)
class TemporalMixerWeights:
    feature_count: int
    hidden: int
    lookback: int
    input_weights: list[list[int]]
    output_weights: list[int]
    bias: list[int]
    input_shift: int = 10
    output_divisor: int = 8
    sparse_stride_mask: int = 0x3
    name: str = "deterministic-int8-v1"

    @classmethod
    def deterministic(cls, *, feature_count: int = 64, hidden: int = 16, lookback: int = 32) -> "TemporalMixerWeights":
        return cls(
            feature_count=feature_count,
            hidden=hidden,
            lookback=lookback,
            input_weights=[[deterministic_weight(h, f) for f in range(feature_count)] for h in range(hidden)],
            output_weights=[deterministic_weight(31, h) for h in range(hidden)],
            bias=[((h * 17 + 5) % 31) - 15 for h in range(hidden)],
        )

    @classmethod
    def from_json(cls, path: str | Path) -> "TemporalMixerWeights":
        data = json.loads(Path(path).read_text())
        if data.get("generator") == "deterministic-int8-v1":
            return cls.deterministic(
                feature_count=int(data["feature_count"]),
                hidden=int(data["hidden"]),
                lookback=int(data["lookback"]),
            )
        return cls(
            feature_count=int(data["feature_count"]),
            hidden=int(data["hidden"]),
            lookback=int(data["lookback"]),
            input_weights=[[int(value) for value in row] for row in data["input_weights"]],
            output_weights=[int(value) for value in data["output_weights"]],
            bias=[int(value) for value in data["bias"]],
            input_shift=int(data.get("input_shift", 10)),
            output_divisor=int(data.get("output_divisor", 8)),
            sparse_stride_mask=int(data.get("sparse_stride_mask", 0x3)),
            name=str(data.get("name", "exported-int8")),
        )

    def to_jsonable(self) -> dict[str, object]:
        return asdict(self)

    def export_json(self, path: str | Path) -> None:
        Path(path).write_text(json.dumps(self.to_jsonable(), indent=2, sort_keys=True) + "\n")


class FloatTemporalMixer:
    """Float approximation of the fixed-point temporal mixer."""

    def __init__(self, weights: TemporalMixerWeights | None = None, *, feature_count: int = 64) -> None:
        self.weights = weights or load_default_weights(feature_count=feature_count)

    def predict(self, window: Sequence[Sequence[int]]) -> FloatInferenceResult:
        hidden_values = self._hidden_values(window)
        raw_logit = 0.0
        for value, weight in zip(hidden_values, self.weights.output_weights):
            raw_logit += value * float(weight)
        score_bps = max(-500.0, min(500.0, raw_logit / self.weights.output_divisor))
        confidence = min(100.0, abs(score_bps) / 5.0)
        return FloatInferenceResult(score_bps, confidence, action_from_score(score_bps), raw_logit)

    def _hidden_values(self, window: Sequence[Sequence[int]]) -> list[float]:
        rows = normalized_rows(window, self.weights.feature_count, self.weights.lookback)
        values: list[float] = []
        for h in range(self.weights.hidden):
            acc = float(self.weights.bias[h] << 8)
            for age, row in enumerate(rows):
                recency = age + 1
                for f, value in enumerate(row):
                    if ((f + h + age) & self.weights.sparse_stride_mask) == 0:
                        acc += float(value) * float(self.weights.input_weights[h][f]) * float(recency)
            values.append(max(-128.0, min(127.0, acc / float(1 << self.weights.input_shift))))
        return values


class FixedPointTemporalMixer:
    """Small int8/int32 sparse temporal mixer with exported deterministic weights."""

    def __init__(
        self,
        weights: TemporalMixerWeights | None = None,
        *,
        feature_count: int = 64,
        hidden: int = 16,
        lookback: int = 32,
    ) -> None:
        self.weights = weights or load_default_weights(feature_count=feature_count, hidden=hidden, lookback=lookback)

    @property
    def feature_count(self) -> int:
        return self.weights.feature_count

    @property
    def hidden(self) -> int:
        return self.weights.hidden

    @property
    def lookback(self) -> int:
        return self.weights.lookback

    def predict(self, window: Sequence[Sequence[int]]) -> InferenceResult:
        rows = normalized_rows(window, self.weights.feature_count, self.weights.lookback)
        hidden_values: list[int] = []
        for h in range(self.weights.hidden):
            acc = self.weights.bias[h] << 8
            for age, row in enumerate(rows):
                recency = age + 1
                for f, value in enumerate(row):
                    if ((f + h + age) & self.weights.sparse_stride_mask) == 0:
                        acc += int(value) * self.weights.input_weights[h][f] * recency
            hidden_values.append(clamp_i8(acc >> self.weights.input_shift))

        raw_logit = 0
        for h, value in enumerate(hidden_values):
            raw_logit += value * self.weights.output_weights[h]

        score_bps = max(-500, min(500, raw_logit // self.weights.output_divisor))
        confidence = min(100, abs(score_bps) // 5)
        return InferenceResult(score_bps, confidence, action_from_score(score_bps), raw_logit)


class QuantizedTemporalMixer(FixedPointTemporalMixer):
    """Backward-compatible name for the fixed-point model."""


@dataclass(frozen=True, slots=True)
class LinearBaseline:
    weights: list[float]
    bias: float

    def predict_score(self, vector: Sequence[float]) -> float:
        return sum(weight * float(value) for weight, value in zip(self.weights, vector)) + self.bias


def load_default_weights(*, feature_count: int = 64, hidden: int = 16, lookback: int = 32) -> TemporalMixerWeights:
    if DEFAULT_WEIGHTS_PATH.exists():
        weights = TemporalMixerWeights.from_json(DEFAULT_WEIGHTS_PATH)
        if (weights.feature_count, weights.hidden, weights.lookback) == (feature_count, hidden, lookback):
            return weights
    return TemporalMixerWeights.deterministic(feature_count=feature_count, hidden=hidden, lookback=lookback)


def normalized_rows(window: Sequence[Sequence[int]], feature_count: int, lookback: int) -> list[list[int]]:
    rows = [list(row[:feature_count]) for row in list(window)[-lookback:]]
    if not rows:
        rows = [[0] * feature_count]
    return [row + [0] * (feature_count - len(row)) if len(row) < feature_count else row for row in rows]


def deterministic_weight(row: int, col: int) -> int:
    """Deterministic pseudo-random int4-like coefficient in [-7, 7]."""

    value = (row * 37 + col * 19 + row * col * 3 + 11) % 15
    return value - 7


def action_from_score(score_bps: float) -> str:
    if score_bps > 10:
        return "BUY"
    if score_bps < -10:
        return "SELL"
    return "HOLD"


def compare_float_fixed(window: Sequence[Sequence[int]], weights: TemporalMixerWeights | None = None) -> dict[str, float | int]:
    selected = weights or load_default_weights()
    fixed = FixedPointTemporalMixer(selected).predict(window)
    floated = FloatTemporalMixer(selected).predict(window)
    return {
        "fixed_raw_logit": fixed.raw_logit,
        "float_raw_logit": floated.raw_logit,
        "fixed_score_bps": fixed.score_bps,
        "float_score_bps": floated.score_bps,
        "score_abs_error_bps": abs(float(fixed.score_bps) - floated.score_bps),
    }


def train_float_baseline(
    examples: Sequence[Sequence[float]],
    labels: Sequence[float],
    *,
    epochs: int = 50,
    learning_rate: float = 0.001,
    l2: float = 0.0001,
) -> LinearBaseline:
    """Train a tiny float linear baseline.

    If PyTorch is installed, callers can build richer models on top of the same
    exported feature matrices. The default path uses plain Python to keep
    validation dependency-free in public CI.
    """

    if len(examples) != len(labels):
        raise ValueError("examples and labels must have the same length")
    if not examples:
        raise ValueError("at least one training example is required")

    width = len(examples[0])
    if width == 0:
        raise ValueError("training examples must contain at least one feature")
    if any(len(example) != width for example in examples):
        raise ValueError("all training examples must have the same width")

    weights = [0.0] * width
    bias = 0.0
    for _ in range(epochs):
        gradients = [0.0] * width
        bias_gradient = 0.0
        for example, label in zip(examples, labels):
            prediction = sum(weight * float(value) for weight, value in zip(weights, example)) + bias
            error = prediction - float(label)
            for index, value in enumerate(example):
                gradients[index] += error * float(value)
            bias_gradient += error
        count = float(len(examples))
        for index in range(width):
            weights[index] -= learning_rate * ((gradients[index] / count) + l2 * weights[index])
        bias -= learning_rate * (bias_gradient / count)
    return LinearBaseline([float(value) for value in weights], float(bias))


def evaluate_regression(model: LinearBaseline, examples: Sequence[Sequence[float]], labels: Sequence[float]) -> dict[str, float]:
    if len(examples) != len(labels):
        raise ValueError("examples and labels must have the same length")
    if not examples:
        return {"count": 0.0, "mse": 0.0, "mae": 0.0}
    errors = [model.predict_score(example) - float(label) for example, label in zip(examples, labels)]
    mse = sum(error * error for error in errors) / len(errors)
    mae = sum(abs(error) for error in errors) / len(errors)
    return {"count": float(len(errors)), "mse": float(mse), "mae": float(mae)}
