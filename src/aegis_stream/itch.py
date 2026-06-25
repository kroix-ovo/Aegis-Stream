"""Nasdaq TotalView-ITCH style parser and canonical event packing.

The parser implements the core order-book mutation messages used by the
Aegis-Stream fast path. It intentionally works on raw concatenated ITCH message
payloads, leaving Ethernet, UDP, SoupBinTCP, or MoldUDP64 framing to the
transport layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import struct
from typing import Iterable, Iterator


class ItchParseError(ValueError):
    """Raised when an ITCH payload cannot be decoded deterministically."""

    def __init__(
        self,
        message: str,
        *,
        offset: int | None = None,
        message_type: str | None = None,
        expected_length: int | None = None,
        available: int | None = None,
    ) -> None:
        super().__init__(message)
        self.offset = offset
        self.message_type = message_type
        self.expected_length = expected_length
        self.available = available


class ItchUnsupportedMessageError(ItchParseError):
    """Raised when a payload contains an unsupported ITCH message type."""


class ItchTruncatedMessageError(ItchParseError):
    """Raised when a payload ends before a complete ITCH message is available."""


class ItchValidationError(ItchParseError):
    """Raised when a syntactically complete ITCH message has invalid fields."""


class EventType(str, Enum):
    ADD = "A"
    ADD_ATTRIBUTED = "F"
    EXECUTE = "E"
    EXECUTE_WITH_PRICE = "C"
    CANCEL = "X"
    DELETE = "D"
    REPLACE = "U"
    TRADE = "P"


MESSAGE_LENGTHS: dict[str, int] = {
    "A": 36,
    "F": 40,
    "E": 31,
    "C": 36,
    "X": 23,
    "D": 19,
    "U": 35,
    "P": 44,
}

EVENT_CODE: dict[EventType, int] = {
    EventType.ADD: 1,
    EventType.ADD_ATTRIBUTED: 1,
    EventType.EXECUTE: 2,
    EventType.EXECUTE_WITH_PRICE: 2,
    EventType.CANCEL: 3,
    EventType.DELETE: 4,
    EventType.REPLACE: 5,
    EventType.TRADE: 6,
}


@dataclass(frozen=True, slots=True)
class CanonicalEvent:
    """Fixed semantic representation used by software and RTL scoreboards."""

    event_type: EventType
    stock_locate: int
    tracking_number: int
    timestamp_ns: int
    order_ref: int = 0
    side: str = ""
    shares: int = 0
    stock: str = ""
    price: int = 0
    match_number: int = 0
    old_order_ref: int = 0
    new_order_ref: int = 0
    printable: str = ""
    attribution: str = ""

    @property
    def symbol(self) -> str:
        return self.stock.strip()

    @property
    def side_flag(self) -> int:
        if self.side == "B":
            return 1
        if self.side == "S":
            return 2
        return 0

    def to_word256(self) -> int:
        """Pack into the 256-bit event word used by the RTL package."""

        order_ref = self.order_ref or self.old_order_ref
        misc = ((self.tracking_number & 0xFFFF) << 16) | (self.match_number & 0xFFFF)
        word = 0
        word |= (EVENT_CODE[self.event_type] & 0xFF) << 248
        word |= (self.stock_locate & 0xFFFF) << 232
        word |= (order_ref & 0xFFFFFFFFFFFFFFFF) << 168
        word |= (self.price & 0xFFFFFFFF) << 136
        word |= (self.shares & 0xFFFFFFFF) << 104
        word |= (self.side_flag & 0xFF) << 96
        word |= (self.timestamp_ns & 0xFFFFFFFFFFFFFFFF) << 32
        word |= misc & 0xFFFFFFFF
        return word


def _timestamp_from_6(raw: bytes) -> int:
    if len(raw) != 6:
        raise ItchTruncatedMessageError("ITCH timestamps are 6 bytes", expected_length=6, available=len(raw))
    return int.from_bytes(raw, "big")


def _timestamp_to_6(timestamp_ns: int) -> bytes:
    if not 0 <= timestamp_ns < (1 << 48):
        raise ValueError("ITCH timestamp must fit in 48 bits")
    return timestamp_ns.to_bytes(6, "big")


def _stock(raw: bytes, *, offset: int = 0) -> str:
    try:
        return raw.decode("ascii").strip()
    except UnicodeDecodeError as exc:
        raise ItchValidationError("stock field is not ASCII", offset=offset) from exc


def _stock_bytes(stock: str) -> bytes:
    encoded = stock.encode("ascii")
    if len(encoded) > 8:
        raise ValueError("ITCH stock field is at most 8 ASCII bytes")
    return encoded.ljust(8, b" ")


def parse_messages(payload: bytes, *, validate: bool = True) -> list[CanonicalEvent]:
    """Parse a payload containing one or more concatenated ITCH messages."""

    return list(iter_messages(payload, validate=validate))


def iter_messages(payload: bytes, *, validate: bool = True, start_offset: int = 0) -> Iterator[CanonicalEvent]:
    offset = 0
    while offset < len(payload):
        raw_type = _message_type(payload[offset])
        length = MESSAGE_LENGTHS.get(raw_type)
        if length is None:
            raise ItchUnsupportedMessageError(
                f"unsupported ITCH message type {raw_type!r} at byte {start_offset + offset}",
                offset=start_offset + offset,
                message_type=raw_type,
            )
        end = offset + length
        if end > len(payload):
            raise ItchTruncatedMessageError(
                f"truncated ITCH {raw_type} message at byte {offset}: "
                f"need {length}, have {len(payload) - offset}",
                offset=start_offset + offset,
                message_type=raw_type,
                expected_length=length,
                available=len(payload) - offset,
            )
        yield _parse_one(payload[offset:end], offset=start_offset + offset, validate=validate)
        offset = end


class ItchStreamDecoder:
    """Incremental parser for ITCH messages split across replay chunks."""

    def __init__(self, *, validate: bool = True) -> None:
        self.validate = validate
        self._buffer = bytearray()
        self._base_offset = 0

    @property
    def buffered_bytes(self) -> int:
        return len(self._buffer)

    def feed(self, chunk: bytes) -> list[CanonicalEvent]:
        self._buffer.extend(chunk)
        events: list[CanonicalEvent] = []
        offset = 0
        while offset < len(self._buffer):
            raw_type = _message_type(self._buffer[offset])
            length = MESSAGE_LENGTHS.get(raw_type)
            absolute_offset = self._base_offset + offset
            if length is None:
                raise ItchUnsupportedMessageError(
                    f"unsupported ITCH message type {raw_type!r} at byte {absolute_offset}",
                    offset=absolute_offset,
                    message_type=raw_type,
                )
            if offset + length > len(self._buffer):
                break
            message = bytes(self._buffer[offset : offset + length])
            events.append(_parse_one(message, offset=absolute_offset, validate=self.validate))
            offset += length

        if offset:
            del self._buffer[:offset]
            self._base_offset += offset
        return events

    def flush(self) -> list[CanonicalEvent]:
        events = self.feed(b"")
        if self._buffer:
            raw_type = _message_type(self._buffer[0])
            length = MESSAGE_LENGTHS.get(raw_type, 0)
            raise ItchTruncatedMessageError(
                f"truncated ITCH {raw_type} message at byte {self._base_offset}: "
                f"need {length}, have {len(self._buffer)}",
                offset=self._base_offset,
                message_type=raw_type,
                expected_length=length,
                available=len(self._buffer),
            )
        return events


def _message_type(raw: int) -> str:
    if 32 <= raw <= 126:
        return chr(raw)
    return f"0x{raw:02x}"


def _parse_header(message: bytes) -> tuple[int, int, int]:
    stock_locate, tracking_number = struct.unpack_from("!HH", message, 1)
    timestamp_ns = _timestamp_from_6(message[5:11])
    return stock_locate, tracking_number, timestamp_ns


def _parse_one(message: bytes, *, offset: int = 0, validate: bool = True) -> CanonicalEvent:
    raw_type = chr(message[0])
    stock_locate, tracking_number, timestamp_ns = _parse_header(message)

    if raw_type in {"A", "F"}:
        order_ref = struct.unpack_from("!Q", message, 11)[0]
        side = chr(message[19])
        shares = struct.unpack_from("!I", message, 20)[0]
        stock = _stock(message[24:32], offset=offset + 24)
        price = struct.unpack_from("!I", message, 32)[0]
        attribution = _stock(message[36:40], offset=offset + 36) if raw_type == "F" else ""
        if validate:
            _validate_side(side, offset=offset + 19)
            _validate_positive("shares", shares, offset=offset + 20)
            _validate_positive("price", price, offset=offset + 32)
        return CanonicalEvent(
            EventType(raw_type),
            stock_locate,
            tracking_number,
            timestamp_ns,
            order_ref=order_ref,
            side=side,
            shares=shares,
            stock=stock,
            price=price,
            attribution=attribution,
        )

    if raw_type in {"E", "C"}:
        order_ref = struct.unpack_from("!Q", message, 11)[0]
        shares = struct.unpack_from("!I", message, 19)[0]
        match_number = struct.unpack_from("!Q", message, 23)[0]
        printable = ""
        price = 0
        if raw_type == "C":
            printable = chr(message[31])
            price = struct.unpack_from("!I", message, 32)[0]
            if validate:
                _validate_printable(printable, offset=offset + 31)
                _validate_positive("price", price, offset=offset + 32)
        if validate:
            _validate_positive("shares", shares, offset=offset + 19)
        return CanonicalEvent(
            EventType(raw_type),
            stock_locate,
            tracking_number,
            timestamp_ns,
            order_ref=order_ref,
            shares=shares,
            price=price,
            match_number=match_number,
            printable=printable,
        )

    if raw_type == "X":
        order_ref = struct.unpack_from("!Q", message, 11)[0]
        shares = struct.unpack_from("!I", message, 19)[0]
        if validate:
            _validate_positive("shares", shares, offset=offset + 19)
        return CanonicalEvent(
            EventType.CANCEL,
            stock_locate,
            tracking_number,
            timestamp_ns,
            order_ref=order_ref,
            shares=shares,
        )

    if raw_type == "D":
        order_ref = struct.unpack_from("!Q", message, 11)[0]
        return CanonicalEvent(
            EventType.DELETE,
            stock_locate,
            tracking_number,
            timestamp_ns,
            order_ref=order_ref,
        )

    if raw_type == "U":
        old_order_ref = struct.unpack_from("!Q", message, 11)[0]
        new_order_ref = struct.unpack_from("!Q", message, 19)[0]
        shares = struct.unpack_from("!I", message, 27)[0]
        price = struct.unpack_from("!I", message, 31)[0]
        if validate:
            if old_order_ref == new_order_ref:
                raise ItchValidationError("replace old and new order references match", offset=offset + 11)
            _validate_positive("shares", shares, offset=offset + 27)
            _validate_positive("price", price, offset=offset + 31)
        return CanonicalEvent(
            EventType.REPLACE,
            stock_locate,
            tracking_number,
            timestamp_ns,
            old_order_ref=old_order_ref,
            new_order_ref=new_order_ref,
            shares=shares,
            price=price,
        )

    if raw_type == "P":
        order_ref = struct.unpack_from("!Q", message, 11)[0]
        side = chr(message[19])
        shares = struct.unpack_from("!I", message, 20)[0]
        stock = _stock(message[24:32], offset=offset + 24)
        price = struct.unpack_from("!I", message, 32)[0]
        match_number = struct.unpack_from("!Q", message, 36)[0]
        if validate:
            _validate_side(side, offset=offset + 19)
            _validate_positive("shares", shares, offset=offset + 20)
            _validate_positive("price", price, offset=offset + 32)
        return CanonicalEvent(
            EventType.TRADE,
            stock_locate,
            tracking_number,
            timestamp_ns,
            order_ref=order_ref,
            side=side,
            shares=shares,
            stock=stock,
            price=price,
            match_number=match_number,
        )

    raise ItchUnsupportedMessageError(f"unsupported ITCH message type {raw_type!r}", offset=offset, message_type=raw_type)


def _validate_side(side: str, *, offset: int) -> None:
    if side not in {"B", "S"}:
        raise ItchValidationError(f"invalid order side {side!r}", offset=offset)


def _validate_printable(printable: str, *, offset: int) -> None:
    if printable not in {"Y", "N"}:
        raise ItchValidationError(f"invalid printable flag {printable!r}", offset=offset)


def _validate_positive(field: str, value: int, *, offset: int) -> None:
    if value <= 0:
        raise ItchValidationError(f"{field} must be positive", offset=offset)


def encode_add(
    *,
    order_ref: int,
    side: str,
    shares: int,
    stock: str,
    price: int,
    timestamp_ns: int,
    stock_locate: int = 1,
    tracking_number: int = 1,
    attribution: str | None = None,
) -> bytes:
    msg_type = b"F" if attribution is not None else b"A"
    base = (
        msg_type
        + struct.pack("!HH", stock_locate, tracking_number)
        + _timestamp_to_6(timestamp_ns)
        + struct.pack("!Q", order_ref)
        + side.encode("ascii")
        + struct.pack("!I", shares)
        + _stock_bytes(stock)
        + struct.pack("!I", price)
    )
    if attribution is not None:
        return base + attribution.encode("ascii").ljust(4, b" ")[:4]
    return base


def encode_execute(
    *,
    order_ref: int,
    shares: int,
    match_number: int,
    timestamp_ns: int,
    stock_locate: int = 1,
    tracking_number: int = 1,
    price: int | None = None,
    printable: str = "Y",
) -> bytes:
    msg_type = b"C" if price is not None else b"E"
    base = (
        msg_type
        + struct.pack("!HH", stock_locate, tracking_number)
        + _timestamp_to_6(timestamp_ns)
        + struct.pack("!QIQ", order_ref, shares, match_number)
    )
    if price is not None:
        return base + printable.encode("ascii") + struct.pack("!I", price)
    return base


def encode_cancel(
    *,
    order_ref: int,
    shares: int,
    timestamp_ns: int,
    stock_locate: int = 1,
    tracking_number: int = 1,
) -> bytes:
    return (
        b"X"
        + struct.pack("!HH", stock_locate, tracking_number)
        + _timestamp_to_6(timestamp_ns)
        + struct.pack("!QI", order_ref, shares)
    )


def encode_delete(
    *,
    order_ref: int,
    timestamp_ns: int,
    stock_locate: int = 1,
    tracking_number: int = 1,
) -> bytes:
    return (
        b"D"
        + struct.pack("!HH", stock_locate, tracking_number)
        + _timestamp_to_6(timestamp_ns)
        + struct.pack("!Q", order_ref)
    )


def encode_replace(
    *,
    old_order_ref: int,
    new_order_ref: int,
    shares: int,
    price: int,
    timestamp_ns: int,
    stock_locate: int = 1,
    tracking_number: int = 1,
) -> bytes:
    return (
        b"U"
        + struct.pack("!HH", stock_locate, tracking_number)
        + _timestamp_to_6(timestamp_ns)
        + struct.pack("!QQII", old_order_ref, new_order_ref, shares, price)
    )


def encode_trade(
    *,
    order_ref: int,
    side: str,
    shares: int,
    stock: str,
    price: int,
    match_number: int,
    timestamp_ns: int,
    stock_locate: int = 1,
    tracking_number: int = 1,
) -> bytes:
    return (
        b"P"
        + struct.pack("!HH", stock_locate, tracking_number)
        + _timestamp_to_6(timestamp_ns)
        + struct.pack("!Q", order_ref)
        + side.encode("ascii")
        + struct.pack("!I", shares)
        + _stock_bytes(stock)
        + struct.pack("!IQ", price, match_number)
    )


def demo_payload() -> bytes:
    """Small deterministic trace used by tests and CLI demos."""

    messages: Iterable[bytes] = [
        encode_add(order_ref=1001, side="B", shares=300, stock="AEGIS", price=100_0000, timestamp_ns=100),
        encode_add(order_ref=1002, side="S", shares=250, stock="AEGIS", price=100_0200, timestamp_ns=120),
        encode_add(order_ref=1003, side="B", shares=150, stock="AEGIS", price=99_9900, timestamp_ns=140),
        encode_execute(order_ref=1001, shares=75, match_number=9001, timestamp_ns=180),
        encode_cancel(order_ref=1002, shares=50, timestamp_ns=220),
        encode_replace(old_order_ref=1003, new_order_ref=1004, shares=200, price=100_0050, timestamp_ns=260),
        encode_trade(
            order_ref=7777,
            side="B",
            shares=40,
            stock="AEGIS",
            price=100_0100,
            match_number=9002,
            timestamp_ns=300,
        ),
    ]
    return b"".join(messages)
