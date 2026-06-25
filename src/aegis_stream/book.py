"""Deterministic order-reference and top-of-book golden model."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

from .itch import CanonicalEvent, EventType


class BookError(RuntimeError):
    """Raised when an event would make the software book inconsistent."""


@dataclass(frozen=True, slots=True)
class BookIssue:
    message: str
    symbol: str = ""


@dataclass(frozen=True, slots=True)
class Order:
    order_ref: int
    symbol: str
    side: str
    price: int
    shares: int


@dataclass(frozen=True, slots=True)
class Level:
    price: int
    shares: int


@dataclass(frozen=True, slots=True)
class BookSnapshot:
    symbol: str
    bids: tuple[Level, ...]
    asks: tuple[Level, ...]
    last_event_type: EventType
    event_count: int
    trade_count: int

    @property
    def best_bid(self) -> Level | None:
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> Level | None:
        return self.asks[0] if self.asks else None

    @property
    def spread(self) -> int:
        if self.best_bid is None or self.best_ask is None:
            return 0
        return self.best_ask.price - self.best_bid.price

    def depth_signature(self, *, top_k: int | None = None) -> tuple[tuple[tuple[int, int], ...], tuple[tuple[int, int], ...]]:
        bids = self.bids[:top_k] if top_k is not None else self.bids
        asks = self.asks[:top_k] if top_k is not None else self.asks
        return (
            tuple((level.price, level.shares) for level in bids),
            tuple((level.price, level.shares) for level in asks),
        )


@dataclass(frozen=True, slots=True)
class ReplayMismatch:
    event_index: int
    symbol: str
    side: str
    expected: tuple[tuple[int, int], ...]
    actual: tuple[tuple[int, int], ...]
    message: str


class OrderBookShard:
    """Single-shard software reference for the hardware book-state tile."""

    def __init__(self, *, symbol: str = "AEGIS", top_k: int = 32, strict: bool = True) -> None:
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        self.symbol = symbol
        self.top_k = top_k
        self.strict = strict
        self.orders: dict[int, Order] = {}
        self._bids: dict[int, int] = {}
        self._asks: dict[int, int] = {}
        self.event_count = 0
        self.trade_count = 0
        self.issues: list[BookIssue] = []

    def apply_event(self, event: CanonicalEvent) -> BookSnapshot:
        if event.event_type in {EventType.ADD, EventType.ADD_ATTRIBUTED}:
            self._add(event.order_ref, event.symbol or self.symbol, event.side, event.price, event.shares)
        elif event.event_type in {EventType.EXECUTE, EventType.EXECUTE_WITH_PRICE, EventType.CANCEL}:
            self._decrement(event.order_ref, event.shares)
        elif event.event_type == EventType.DELETE:
            self._delete(event.order_ref)
        elif event.event_type == EventType.REPLACE:
            self._replace(event.old_order_ref, event.new_order_ref, event.shares, event.price)
        elif event.event_type == EventType.TRADE:
            self.trade_count += 1
        else:
            raise BookError(f"unsupported event type {event.event_type}")

        self.event_count += 1
        invariant_errors = self.check_invariants()
        if invariant_errors:
            self._fail("; ".join(invariant_errors))
        return self.snapshot(last_event_type=event.event_type)

    def snapshot(self, *, last_event_type: EventType = EventType.TRADE) -> BookSnapshot:
        bids = tuple(Level(price, qty) for price, qty in sorted(self._bids.items(), reverse=True)[: self.top_k])
        asks = tuple(Level(price, qty) for price, qty in sorted(self._asks.items())[: self.top_k])
        return BookSnapshot(self.symbol, bids, asks, last_event_type, self.event_count, self.trade_count)

    def _add(self, order_ref: int, symbol: str, side: str, price: int, shares: int) -> None:
        if order_ref in self.orders:
            self._fail(f"duplicate live order reference {order_ref}")
            return
        if side not in {"B", "S"}:
            self._fail(f"invalid side {side!r} for order {order_ref}")
            return
        if shares <= 0:
            self._fail(f"non-positive share quantity {shares} for order {order_ref}")
            return
        if price <= 0:
            self._fail(f"non-positive price {price} for order {order_ref}")
            return

        order = Order(order_ref, symbol, side, price, shares)
        self.orders[order_ref] = order
        self._add_level(order.side, order.price, order.shares)

    def _decrement(self, order_ref: int, shares: int) -> None:
        order = self.orders.get(order_ref)
        if order is None:
            self._fail(f"cannot decrement missing order {order_ref}")
            return
        if shares <= 0:
            self._fail(f"non-positive decrement {shares} for order {order_ref}")
            return
        if shares > order.shares:
            self._fail(f"decrement {shares} exceeds remaining quantity {order.shares} for order {order_ref}")
            return

        self._add_level(order.side, order.price, -shares)
        remaining = order.shares - shares
        if remaining == 0:
            del self.orders[order_ref]
        else:
            self.orders[order_ref] = Order(order.order_ref, order.symbol, order.side, order.price, remaining)

    def _delete(self, order_ref: int) -> None:
        order = self.orders.get(order_ref)
        if order is None:
            self._fail(f"cannot delete missing order {order_ref}")
            return
        self._add_level(order.side, order.price, -order.shares)
        del self.orders[order_ref]

    def _replace(self, old_order_ref: int, new_order_ref: int, shares: int, price: int) -> None:
        old = self.orders.get(old_order_ref)
        if old is None:
            self._fail(f"cannot replace missing order {old_order_ref}")
            return
        if new_order_ref in self.orders:
            self._fail(f"replace would create duplicate order {new_order_ref}")
            return
        if old_order_ref == new_order_ref:
            self._fail(f"replace old and new order references match for {old_order_ref}")
            return
        if shares <= 0:
            self._fail(f"non-positive replacement quantity {shares} for order {new_order_ref}")
            return
        if price <= 0:
            self._fail(f"non-positive replacement price {price} for order {new_order_ref}")
            return

        self._add_level(old.side, old.price, -old.shares)
        del self.orders[old_order_ref]
        self._add(new_order_ref, old.symbol, old.side, price, shares)

    def _add_level(self, side: str, price: int, delta: int) -> None:
        levels = self._bids if side == "B" else self._asks
        updated = levels.get(price, 0) + delta
        if updated < 0:
            self._fail(f"negative aggregate depth at price {price}")
            return
        if updated == 0:
            levels.pop(price, None)
        else:
            levels[price] = updated

    def _fail(self, message: str) -> None:
        self.issues.append(BookIssue(message, self.symbol))
        if self.strict:
            raise BookError(message)

    def check_invariants(self) -> list[str]:
        expected_bids: dict[int, int] = {}
        expected_asks: dict[int, int] = {}
        for order in self.orders.values():
            levels = expected_bids if order.side == "B" else expected_asks if order.side == "S" else None
            if levels is None:
                return [f"invalid side {order.side!r} stored for order {order.order_ref}"]
            if order.shares <= 0:
                return [f"non-positive live quantity {order.shares} for order {order.order_ref}"]
            levels[order.price] = levels.get(order.price, 0) + order.shares

        errors: list[str] = []
        if expected_bids != self._bids:
            errors.append("bid depth does not match live orders")
        if expected_asks != self._asks:
            errors.append("ask depth does not match live orders")
        if any(quantity <= 0 for quantity in self._bids.values()) or any(quantity <= 0 for quantity in self._asks.values()):
            errors.append("aggregate depth contains non-positive quantity")
        return errors


class MultiSymbolOrderBook:
    """Golden book dispatcher keyed by symbol with an order-reference index."""

    def __init__(self, *, top_k: int = 32, strict: bool = True, default_symbol: str = "AEGIS") -> None:
        self.top_k = top_k
        self.strict = strict
        self.default_symbol = default_symbol
        self.shards: dict[str, OrderBookShard] = {}
        self.order_to_symbol: dict[int, str] = {}
        self.event_count = 0
        self.issues: list[BookIssue] = []

    def apply_event(self, event: CanonicalEvent) -> BookSnapshot:
        symbol = self._symbol_for_event(event)
        shard = self._shard(symbol)
        issue_start = len(shard.issues)
        try:
            snapshot = shard.apply_event(event)
        except BookError as exc:
            self.issues.extend(shard.issues[issue_start:])
            if self.strict:
                raise
            self.issues.append(BookIssue(str(exc), symbol))
            snapshot = shard.snapshot(last_event_type=event.event_type)
        else:
            self.issues.extend(shard.issues[issue_start:])

        self._update_order_index(event, shard, symbol)
        self.event_count += 1
        return snapshot

    def snapshot(self, symbol: str) -> BookSnapshot:
        return self._shard(symbol).snapshot()

    def snapshots(self) -> dict[str, BookSnapshot]:
        return {symbol: shard.snapshot() for symbol, shard in sorted(self.shards.items())}

    def _shard(self, symbol: str) -> OrderBookShard:
        if symbol not in self.shards:
            self.shards[symbol] = OrderBookShard(symbol=symbol, top_k=self.top_k, strict=self.strict)
        return self.shards[symbol]

    def _symbol_for_event(self, event: CanonicalEvent) -> str:
        if event.event_type in {EventType.ADD, EventType.ADD_ATTRIBUTED, EventType.TRADE} and event.symbol:
            return event.symbol
        if event.event_type == EventType.REPLACE:
            return self.order_to_symbol.get(event.old_order_ref, event.symbol or self._locate_symbol(event))
        if event.order_ref:
            return self.order_to_symbol.get(event.order_ref, event.symbol or self._locate_symbol(event))
        return event.symbol or self._locate_symbol(event)

    def _locate_symbol(self, event: CanonicalEvent) -> str:
        if event.stock_locate:
            return f"LOCATE-{event.stock_locate}"
        return self.default_symbol

    def _update_order_index(self, event: CanonicalEvent, shard: OrderBookShard, symbol: str) -> None:
        if event.event_type in {EventType.ADD, EventType.ADD_ATTRIBUTED}:
            if event.order_ref in shard.orders:
                self.order_to_symbol[event.order_ref] = symbol
        elif event.event_type in {EventType.EXECUTE, EventType.EXECUTE_WITH_PRICE, EventType.CANCEL}:
            if event.order_ref not in shard.orders:
                self.order_to_symbol.pop(event.order_ref, None)
        elif event.event_type == EventType.DELETE:
            self.order_to_symbol.pop(event.order_ref, None)
        elif event.event_type == EventType.REPLACE:
            self.order_to_symbol.pop(event.old_order_ref, None)
            if event.new_order_ref in shard.orders:
                self.order_to_symbol[event.new_order_ref] = symbol


def compare_snapshot_depth(
    expected: BookSnapshot,
    actual: BookSnapshot,
    *,
    event_index: int = -1,
    top_k: int | None = None,
) -> list[ReplayMismatch]:
    expected_bids, expected_asks = expected.depth_signature(top_k=top_k)
    actual_bids, actual_asks = actual.depth_signature(top_k=top_k)
    mismatches: list[ReplayMismatch] = []
    if expected_bids != actual_bids:
        mismatches.append(
            ReplayMismatch(event_index, expected.symbol, "B", expected_bids, actual_bids, "bid top-K mismatch")
        )
    if expected_asks != actual_asks:
        mismatches.append(
            ReplayMismatch(event_index, expected.symbol, "S", expected_asks, actual_asks, "ask top-K mismatch")
        )
    return mismatches


def replay_mismatches(
    events: Iterable[CanonicalEvent],
    expected_book: MultiSymbolOrderBook,
    actual_book: MultiSymbolOrderBook,
    *,
    top_k: int | None = None,
) -> list[ReplayMismatch]:
    mismatches: list[ReplayMismatch] = []
    for index, event in enumerate(events):
        expected = expected_book.apply_event(event)
        actual = actual_book.apply_event(event)
        mismatches.extend(compare_snapshot_depth(expected, actual, event_index=index, top_k=top_k))
    return mismatches
