"""Deterministic order-reference and top-of-book golden model."""

from __future__ import annotations

from dataclasses import dataclass

from .itch import CanonicalEvent, EventType


class BookError(RuntimeError):
    """Raised when an event would make the software book inconsistent."""


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
        if self.strict:
            raise BookError(message)
