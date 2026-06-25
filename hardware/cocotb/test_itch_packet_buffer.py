from __future__ import annotations

import cocotb
from cocotb.triggers import RisingEdge, Timer

from aegis_stream.itch import encode_add, encode_cancel

from cocotb_helpers import keep_for, payload_to_word, start_clock_and_reset


async def _reset(dut) -> None:
    dut.s_payload_tdata.value = 0
    dut.s_payload_tkeep.value = 0
    dut.s_payload_tvalid.value = 0
    dut.s_payload_tlast.value = 0
    dut.s_payload_timestamp_ns.value = 0
    dut.m_payload_tready.value = 1
    await start_clock_and_reset(dut)


async def _beat(dut, payload: bytes, *, last: int = 1, timestamp_ns: int = 0) -> None:
    dut.s_payload_tdata.value = payload_to_word(payload)
    dut.s_payload_tkeep.value = keep_for(len(payload))
    dut.s_payload_tlast.value = last
    dut.s_payload_timestamp_ns.value = timestamp_ns
    dut.s_payload_tvalid.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.s_payload_tvalid.value = 0
    dut.s_payload_tdata.value = 0
    dut.s_payload_tkeep.value = 0
    dut.s_payload_tlast.value = 0


async def _accept_output(dut) -> None:
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")


def _payload_prefix(dut, length: int) -> bytes:
    word = int(dut.m_payload_tdata.value)
    return bytes((word >> (512 - ((index + 1) * 8))) & 0xFF for index in range(length))


@cocotb.test()
async def cross_beat_message_is_reassembled_at_byte_zero(dut) -> None:
    await _reset(dut)
    message = encode_add(order_ref=1, side="B", shares=100, stock="AEGIS", price=1000, timestamp_ns=10)

    await _beat(dut, message[:5], last=0, timestamp_ns=123)
    assert int(dut.m_payload_tvalid.value) == 0
    await _beat(dut, message[5:], last=1, timestamp_ns=124)

    assert int(dut.m_payload_tvalid.value) == 1
    assert int(dut.m_error.value) == 0
    assert int(dut.m_payload_tkeep.value) == keep_for(len(message))
    assert int(dut.m_payload_timestamp_ns.value) == 123
    assert _payload_prefix(dut, len(message)) == message


@cocotb.test()
async def concatenated_messages_emit_one_aligned_record_at_a_time(dut) -> None:
    await _reset(dut)
    add = encode_add(order_ref=1, side="B", shares=100, stock="AEGIS", price=1000, timestamp_ns=10)
    cancel = encode_cancel(order_ref=1, shares=25, timestamp_ns=11)
    await _beat(dut, add + cancel, last=1, timestamp_ns=10)

    assert int(dut.m_payload_tvalid.value) == 1
    assert int(dut.m_payload_tkeep.value) == keep_for(len(add))
    assert _payload_prefix(dut, len(add)) == add

    await _accept_output(dut)
    assert int(dut.m_payload_tvalid.value) == 1
    assert int(dut.m_payload_tkeep.value) == keep_for(len(cancel))
    assert _payload_prefix(dut, len(cancel)) == cancel


@cocotb.test()
async def truncated_tail_reports_error_two(dut) -> None:
    await _reset(dut)
    message = encode_add(order_ref=1, side="B", shares=100, stock="AEGIS", price=1000, timestamp_ns=10)
    await _beat(dut, message[:7], last=1, timestamp_ns=55)

    assert int(dut.m_payload_tvalid.value) == 1
    assert int(dut.m_error.value) == 2
    assert int(dut.m_payload_tkeep.value) == keep_for(7)
    assert _payload_prefix(dut, 7) == message[:7]
