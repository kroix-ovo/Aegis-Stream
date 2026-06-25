from __future__ import annotations

import cocotb
from cocotb.triggers import RisingEdge, Timer

from aegis_stream.itch import (
    encode_add,
    encode_cancel,
    encode_delete,
    encode_execute,
    encode_replace,
    encode_trade,
    parse_messages,
)

from cocotb_helpers import keep_for, payload_to_word, start_clock_and_reset, unpack_event


async def _reset(dut) -> None:
    dut.s_payload_tdata.value = 0
    dut.s_payload_tkeep.value = 0
    dut.s_payload_tvalid.value = 0
    dut.s_payload_tlast.value = 0
    dut.s_payload_timestamp_ns.value = 0
    dut.m_event_tready.value = 1
    await start_clock_and_reset(dut)


async def _drive_payload(dut, payload: bytes, *, timestamp_ns: int = 0, keep_len: int | None = None, last: int = 1) -> None:
    dut.s_payload_tdata.value = payload_to_word(payload)
    dut.s_payload_tkeep.value = keep_for(len(payload) if keep_len is None else keep_len)
    dut.s_payload_timestamp_ns.value = timestamp_ns
    dut.s_payload_tlast.value = last
    dut.s_payload_tvalid.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.s_payload_tvalid.value = 0
    dut.s_payload_tdata.value = 0
    dut.s_payload_tkeep.value = 0
    dut.s_payload_tlast.value = 0


def _assert_event_word(dut, expected: int) -> None:
    actual = int(dut.m_event_tdata.value)
    assert actual == expected, f"event word mismatch: got 0x{actual:064x}, expected 0x{expected:064x}"


@cocotb.test()
async def supported_messages_match_python_parser(dut) -> None:
    await _reset(dut)
    messages = [
        encode_add(
            order_ref=1001,
            side="B",
            shares=300,
            stock="AEGIS",
            price=1_000_000,
            timestamp_ns=10,
            stock_locate=7,
            tracking_number=11,
        ),
        encode_add(
            order_ref=1002,
            side="S",
            shares=250,
            stock="AEGIS",
            price=1_000_100,
            timestamp_ns=11,
            stock_locate=7,
            tracking_number=12,
            attribution="KRX",
        ),
        encode_execute(
            order_ref=1001,
            shares=25,
            match_number=0xABCDEF0123456789,
            timestamp_ns=12,
            stock_locate=7,
            tracking_number=13,
        ),
        encode_execute(
            order_ref=1001,
            shares=10,
            match_number=0xABCDEF0123454321,
            timestamp_ns=13,
            stock_locate=7,
            tracking_number=14,
            price=999_900,
            printable="Y",
        ),
        encode_cancel(order_ref=1001, shares=15, timestamp_ns=14, stock_locate=7, tracking_number=15),
        encode_delete(order_ref=1002, timestamp_ns=15, stock_locate=7, tracking_number=16),
        encode_replace(
            old_order_ref=1001,
            new_order_ref=2001,
            shares=275,
            price=1_000_050,
            timestamp_ns=16,
            stock_locate=7,
            tracking_number=17,
        ),
        encode_trade(
            order_ref=3001,
            side="B",
            shares=50,
            stock="AEGIS",
            price=1_000_025,
            match_number=0x1111222233334444,
            timestamp_ns=17,
            stock_locate=7,
            tracking_number=18,
        ),
    ]

    for payload in messages:
        expected = parse_messages(payload)[0].to_word256()
        await _drive_payload(dut, payload)
        assert int(dut.m_event_tvalid.value) == 1
        assert int(dut.m_error.value) == 0, f"{chr(payload[0])} returned error {int(dut.m_error.value)}"
        _assert_event_word(dut, expected)
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")


@cocotb.test()
async def malformed_and_cross_message_payloads_report_errors(dut) -> None:
    await _reset(dut)

    unsupported = b"Z"
    await _drive_payload(dut, unsupported, timestamp_ns=1234)
    assert int(dut.m_event_tvalid.value) == 1
    assert int(dut.m_error.value) == 1
    decoded = unpack_event(int(dut.m_event_tdata.value))
    assert decoded["event_type"] == 0
    assert decoded["timestamp_ns"] == 1234

    await RisingEdge(dut.clk)
    truncated = encode_add(order_ref=1, side="B", shares=1, stock="AEGIS", price=1, timestamp_ns=1)
    await _drive_payload(dut, truncated, keep_len=12)
    assert int(dut.m_error.value) == 2

    await RisingEdge(dut.clk)
    not_last = encode_cancel(order_ref=1, shares=1, timestamp_ns=2)
    await _drive_payload(dut, not_last, last=0)
    assert int(dut.m_error.value) == 3

    await RisingEdge(dut.clk)
    first = encode_add(order_ref=1, side="B", shares=1, stock="AEGIS", price=1, timestamp_ns=3)
    second = encode_cancel(order_ref=1, shares=1, timestamp_ns=4)
    await _drive_payload(dut, first + second)
    assert int(dut.m_error.value) == 4


@cocotb.test()
async def output_word_holds_under_backpressure(dut) -> None:
    await _reset(dut)
    dut.m_event_tready.value = 0
    payload = encode_add(order_ref=55, side="B", shares=100, stock="AEGIS", price=1000, timestamp_ns=22)
    expected = parse_messages(payload)[0].to_word256()

    await _drive_payload(dut, payload)
    assert int(dut.m_event_tvalid.value) == 1
    _assert_event_word(dut, expected)
    held_word = int(dut.m_event_tdata.value)

    for _ in range(3):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        assert int(dut.m_event_tvalid.value) == 1
        assert int(dut.m_event_tdata.value) == held_word
        assert int(dut.s_payload_tready.value) == 0

    dut.m_event_tready.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert int(dut.m_event_tvalid.value) == 0
