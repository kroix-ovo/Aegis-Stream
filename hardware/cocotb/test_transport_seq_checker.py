from __future__ import annotations

import cocotb
from cocotb.triggers import RisingEdge, Timer

from cocotb_helpers import start_clock_and_reset


async def _reset(dut) -> None:
    dut.reset_counters.value = 0
    dut.packet_valid.value = 0
    dut.packet_sequence.value = 0
    dut.packet_message_count.value = 0
    dut.packet_malformed.value = 0
    await start_clock_and_reset(dut)


async def _packet(dut, sequence: int, count: int, *, malformed: int = 0) -> None:
    dut.packet_sequence.value = sequence
    dut.packet_message_count.value = count
    dut.packet_malformed.value = malformed
    dut.packet_valid.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.packet_valid.value = 0


def _counters(dut) -> dict[str, int]:
    return {
        "expected_sequence": int(dut.expected_sequence.value),
        "packets": int(dut.packets.value),
        "payload_messages": int(dut.payload_messages.value),
        "gaps": int(dut.gaps.value),
        "duplicate_packets": int(dut.duplicate_packets.value),
        "malformed_packets": int(dut.malformed_packets.value),
        "gap_messages": int(dut.gap_messages.value),
    }


@cocotb.test()
async def moldudp64_sequence_counters_track_gaps_and_duplicates(dut) -> None:
    await _reset(dut)
    assert int(dut.packet_ready.value) == 1

    await _packet(dut, 1, 2)
    assert _counters(dut) == {
        "expected_sequence": 3,
        "packets": 1,
        "payload_messages": 2,
        "gaps": 0,
        "duplicate_packets": 0,
        "malformed_packets": 0,
        "gap_messages": 0,
    }

    await _packet(dut, 3, 1)
    assert _counters(dut)["expected_sequence"] == 4

    await _packet(dut, 6, 2)
    counters = _counters(dut)
    assert counters["expected_sequence"] == 8
    assert counters["gaps"] == 1
    assert counters["gap_messages"] == 2
    assert counters["payload_messages"] == 5

    await _packet(dut, 7, 1)
    counters = _counters(dut)
    assert counters["expected_sequence"] == 8
    assert counters["duplicate_packets"] == 1
    assert counters["payload_messages"] == 6

    await _packet(dut, 8, 4, malformed=1)
    counters = _counters(dut)
    assert counters["packets"] == 5
    assert counters["malformed_packets"] == 1
    assert counters["payload_messages"] == 6
    assert counters["expected_sequence"] == 8


@cocotb.test()
async def reset_counters_clears_sequence_state(dut) -> None:
    await _reset(dut)
    await _packet(dut, 10, 2)
    assert _counters(dut)["expected_sequence"] == 12

    dut.reset_counters.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.reset_counters.value = 0
    assert _counters(dut) == {
        "expected_sequence": 0,
        "packets": 0,
        "payload_messages": 0,
        "gaps": 0,
        "duplicate_packets": 0,
        "malformed_packets": 0,
        "gap_messages": 0,
    }
