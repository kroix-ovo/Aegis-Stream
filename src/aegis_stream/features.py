"""Streaming microstructure feature window generation."""

from __future__ import annotations

from collections import Counter, deque
from typing import Sequence

from .book import BookSnapshot, Level
from .itch import CanonicalEvent, EVENT_CODE, EventType


def clamp_i8(value: int) -> int:
    return max(-128, min(127, int(value)))


def _scaled(value: int, divisor: int) -> int:
    if divisor <= 0:
        raise ValueError("divisor must be positive")
    if value >= 0:
        return clamp_i8(value // divisor)
    return clamp_i8(-((-value) // divisor))


class FeatureWindowEngine:
    """Ring-buffer feature engine matching the proposed hardware window."""

    def __init__(self, *, window: int = 128, feature_count: int = 64, event_horizon: int = 32) -> None:
        if window <= 0:
            raise ValueError("window must be positive")
        if feature_count < 16:
            raise ValueError("feature_count must be at least 16")
        self.window = window
        self.feature_count = feature_count
        self.rows: list[list[int]] = [[0] * feature_count for _ in range(window)]
        self.cursor = 0
        self.count = 0
        self.recent_events: deque[EventType] = deque(maxlen=event_horizon)

    def update(self, event: CanonicalEvent, snapshot: BookSnapshot) -> list[int]:
        self.recent_events.append(event.event_type)
        vector = self._build_vector(event, snapshot)
        self.rows[self.cursor] = vector
        self.cursor = (self.cursor + 1) % self.window
        self.count = min(self.count + 1, self.window)
        return vector

    def latest(self) -> list[int]:
        if self.count == 0:
            return [0] * self.feature_count
        return list(self.rows[(self.cursor - 1) % self.window])

    def matrix(self) -> list[list[int]]:
        """Return rows in oldest-to-newest order, left padded until full."""

        if self.count < self.window:
            padding = [[0] * self.feature_count for _ in range(self.window - self.count)]
            return padding + [list(row) for row in self.rows[: self.count]]

        return [list(self.rows[(self.cursor + i) % self.window]) for i in range(self.window)]

    def flattened(self) -> list[int]:
        flat: list[int] = []
        for row in self.matrix():
            flat.extend(row)
        return flat

    def _build_vector(self, event: CanonicalEvent, snapshot: BookSnapshot) -> list[int]:
        bid = snapshot.best_bid
        ask = snapshot.best_ask
        bid_qty = bid.shares if bid else 0
        ask_qty = ask.shares if ask else 0
        total_top_qty = bid_qty + ask_qty
        imbalance = int(round(127 * (bid_qty - ask_qty) / total_top_qty)) if total_top_qty else 0
        mid = ((bid.price if bid else 0) + (ask.price if ask else 0)) // 2 if bid and ask else event.price
        counts = Counter(self.recent_events)

        vector = [0] * self.feature_count
        vector[0] = _scaled(snapshot.spread, 100)
        vector[1] = _scaled(bid_qty, 100)
        vector[2] = _scaled(ask_qty, 100)
        vector[3] = clamp_i8(imbalance)
        vector[4] = clamp_i8(EVENT_CODE[event.event_type])
        vector[5] = 1 if event.side == "B" else -1 if event.side == "S" else 0
        vector[6] = _scaled(event.shares, 100)
        vector[7] = _scaled(event.price - mid, 100)
        vector[8] = _scaled(sum(level.shares for level in snapshot.bids), 100)
        vector[9] = _scaled(sum(level.shares for level in snapshot.asks), 100)
        vector[10] = clamp_i8(counts[EventType.ADD] + counts[EventType.ADD_ATTRIBUTED])
        vector[11] = clamp_i8(counts[EventType.CANCEL])
        vector[12] = clamp_i8(counts[EventType.EXECUTE] + counts[EventType.EXECUTE_WITH_PRICE])
        vector[13] = clamp_i8(counts[EventType.DELETE])
        vector[14] = clamp_i8(counts[EventType.REPLACE])
        vector[15] = clamp_i8(counts[EventType.TRADE])

        self._encode_depth_shape(vector, snapshot.bids, base=16, bid_side=True)
        self._encode_depth_shape(vector, snapshot.asks, base=32, bid_side=False)
        vector[48] = 1 if bid and ask and bid.price >= ask.price else 0
        vector[49] = _scaled(snapshot.event_count, 1)
        vector[50] = _scaled(snapshot.trade_count, 1)
        vector[51] = clamp_i8(len(snapshot.bids))
        vector[52] = clamp_i8(len(snapshot.asks))
        vector[53] = _scaled(event.timestamp_ns, 1_000_000)
        return vector

    def _encode_depth_shape(
        self,
        vector: list[int],
        levels: Sequence[Level],
        *,
        base: int,
        bid_side: bool,
    ) -> None:
        limit = min(8, len(levels), (self.feature_count - base) // 2)
        if limit <= 0:
            return
        anchor = levels[0].price
        sign = 1 if bid_side else -1
        for idx in range(limit):
            level = levels[idx]
            vector[base + idx * 2] = _scaled(sign * (level.price - anchor), 100)
            vector[base + idx * 2 + 1] = _scaled(level.shares, 100)
