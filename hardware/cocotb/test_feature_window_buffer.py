from __future__ import annotations

import cocotb
from cocotb.triggers import RisingEdge, Timer

from cocotb_helpers import start_clock_and_reset


def _pack(values: list[int]) -> int:
    word = 0
    for index, value in enumerate(values):
        word |= (value & 0xFF) << (index * 8)
    return word


async def _reset(dut) -> None:
    dut.feature_valid.value = 0
    dut.feature_tdata.value = 0
    dut.read_age.value = 0
    await start_clock_and_reset(dut)


async def _push(dut, values: list[int]) -> None:
    dut.feature_tdata.value = _pack(values)
    dut.feature_valid.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.feature_valid.value = 0


@cocotb.test()
async def ring_buffer_returns_latest_and_age_indexed_rows(dut) -> None:
    await _reset(dut)
    rows = [[row + col for col in range(64)] for row in range(10)]
    for row in rows:
        await _push(dut, row)

    assert int(dut.rows_seen.value) == 8
    assert int(dut.latest_tdata.value) == _pack(rows[-1])

    dut.read_age.value = 1
    await Timer(1, unit="ns")
    assert int(dut.read_tdata.value) == _pack(rows[-2])

    dut.read_age.value = 7
    await Timer(1, unit="ns")
    assert int(dut.read_tdata.value) == _pack(rows[-8])
