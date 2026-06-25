from __future__ import annotations

import cocotb
from cocotb.triggers import RisingEdge, Timer

from cocotb_helpers import start_clock_and_reset


def _pack_i8(values: list[int]) -> int:
    word = 0
    for index, value in enumerate(values):
        word |= (value & 0xFF) << (index * 8)
    return word


def _signed8(value: int) -> int:
    value &= 0xFF
    return value - 256 if value & 0x80 else value


def _score(value: int, shift: int) -> int:
    shifted = value >> shift
    return max(-500, min(500, shifted))


async def _reset(dut) -> None:
    dut.in_valid.value = 0
    dut.feature_tdata.value = 0
    dut.weight_tdata.value = 0
    dut.bias.value = 0
    dut.output_shift.value = 0
    dut.out_ready.value = 1
    await start_clock_and_reset(dut)


@cocotb.test()
async def int8_dot_product_matches_python_reference(dut) -> None:
    await _reset(dut)
    features = [(index % 17) - 8 for index in range(64)]
    weights = [((index * 5) % 13) - 6 for index in range(64)]
    bias = -17
    raw = bias + sum(_signed8(f) * _signed8(w) for f, w in zip(features, weights))

    dut.feature_tdata.value = _pack_i8(features)
    dut.weight_tdata.value = _pack_i8(weights)
    dut.bias.value = bias & 0xFFFFFFFF
    dut.output_shift.value = 2
    dut.in_valid.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.in_valid.value = 0

    assert int(dut.out_valid.value) == 1
    assert dut.raw_logit.value.to_signed() == raw
    assert dut.score_bps.value.to_signed() == _score(raw, 2)


@cocotb.test()
async def output_holds_under_backpressure(dut) -> None:
    await _reset(dut)
    dut.out_ready.value = 0
    dut.feature_tdata.value = _pack_i8([1] * 64)
    dut.weight_tdata.value = _pack_i8([2] * 64)
    dut.bias.value = 0
    dut.output_shift.value = 0
    dut.in_valid.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.in_valid.value = 0
    held = (dut.raw_logit.value.to_signed(), dut.score_bps.value.to_signed())

    for _ in range(3):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        assert int(dut.out_valid.value) == 1
        assert (dut.raw_logit.value.to_signed(), dut.score_bps.value.to_signed()) == held
