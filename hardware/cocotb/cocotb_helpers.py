"""Shared cocotb helpers for Aegis-Stream RTL scoreboards."""

from __future__ import annotations

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import RisingEdge, Timer


EVENT_TYPE_SHIFT = 248
STOCK_LOCATE_SHIFT = 232
ORDER_REF_SHIFT = 168
PRICE_SHIFT = 136
SHARES_SHIFT = 104
SIDE_FLAGS_SHIFT = 96
TIMESTAMP_SHIFT = 32


def payload_to_word(payload: bytes) -> int:
    """Pack byte 0 into bits 511:504, matching the RTL AXI beat layout."""

    if len(payload) > 64:
        raise ValueError("payload beat is limited to 64 bytes")
    word = 0
    for index, byte in enumerate(payload):
        word |= int(byte) << (512 - ((index + 1) * 8))
    return word


def keep_for(length: int) -> int:
    if not 0 <= length <= 64:
        raise ValueError("tkeep length must be in [0, 64]")
    return (1 << length) - 1 if length else 0


def unpack_event(word: int) -> dict[str, int]:
    return {
        "event_type": (word >> EVENT_TYPE_SHIFT) & 0xFF,
        "stock_locate": (word >> STOCK_LOCATE_SHIFT) & 0xFFFF,
        "order_ref": (word >> ORDER_REF_SHIFT) & 0xFFFFFFFFFFFFFFFF,
        "price": (word >> PRICE_SHIFT) & 0xFFFFFFFF,
        "shares": (word >> SHARES_SHIFT) & 0xFFFFFFFF,
        "side_flags": (word >> SIDE_FLAGS_SHIFT) & 0xFF,
        "timestamp_ns": (word >> TIMESTAMP_SHIFT) & 0xFFFFFFFFFFFFFFFF,
        "misc": word & 0xFFFFFFFF,
    }


async def start_clock_and_reset(dut, *, period_ns: int = 10) -> None:
    cocotb.start_soon(Clock(dut.clk, period_ns, unit="ns").start())
    dut.rst_n.value = 0
    await RisingEdge(dut.clk)
    await RisingEdge(dut.clk)
    dut.rst_n.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
