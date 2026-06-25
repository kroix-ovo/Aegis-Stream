from __future__ import annotations

import cocotb
from cocotb.triggers import RisingEdge, Timer

from cocotb_helpers import start_clock_and_reset


def _unpack_telemetry(word: int) -> dict[str, int]:
    return {
        "ingress_ts": (word >> 320) & 0xFFFFFFFFFFFFFFFF,
        "parser_ts": (word >> 256) & 0xFFFFFFFFFFFFFFFF,
        "book_ts": (word >> 192) & 0xFFFFFFFFFFFFFFFF,
        "feature_ts": (word >> 128) & 0xFFFFFFFFFFFFFFFF,
        "model_ts": (word >> 64) & 0xFFFFFFFFFFFFFFFF,
        "event_id": (word >> 32) & 0xFFFFFFFF,
        "flags": word & 0xFFFFFFFF,
    }


async def _reset(dut) -> None:
    dut.event_id.value = 0
    dut.timestamp_counter.value = 0
    dut.mark_ingress.value = 0
    dut.mark_parser.value = 0
    dut.mark_book.value = 0
    dut.mark_feature.value = 0
    dut.mark_model.value = 0
    dut.telemetry_ready.value = 1
    await start_clock_and_reset(dut)


async def _mark(dut, signal: str, timestamp: int, *, event_id: int = 99) -> None:
    dut.event_id.value = event_id
    dut.timestamp_counter.value = timestamp
    getattr(dut, signal).value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    getattr(dut, signal).value = 0


@cocotb.test()
async def packed_field_layout_matches_contract(dut) -> None:
    await _reset(dut)
    dut.telemetry_ready.value = 0

    await _mark(dut, "mark_ingress", 10, event_id=123)
    await _mark(dut, "mark_parser", 20, event_id=123)
    await _mark(dut, "mark_book", 30, event_id=123)
    await _mark(dut, "mark_feature", 40, event_id=123)
    await _mark(dut, "mark_model", 50, event_id=123)

    assert int(dut.telemetry_valid.value) == 1
    fields = _unpack_telemetry(int(dut.telemetry_data.value))
    assert fields == {
        "ingress_ts": 10,
        "parser_ts": 20,
        "book_ts": 30,
        "feature_ts": 40,
        "model_ts": 50,
        "event_id": 123,
        "flags": 0,
    }


@cocotb.test()
async def telemetry_valid_holds_until_ready(dut) -> None:
    await _reset(dut)
    dut.telemetry_ready.value = 0

    await _mark(dut, "mark_ingress", 100, event_id=7)
    await _mark(dut, "mark_model", 200, event_id=7)
    held_word = int(dut.telemetry_data.value)
    assert int(dut.telemetry_valid.value) == 1

    for _ in range(3):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        assert int(dut.telemetry_valid.value) == 1
        assert int(dut.telemetry_data.value) == held_word

    dut.telemetry_ready.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert int(dut.telemetry_valid.value) == 0
