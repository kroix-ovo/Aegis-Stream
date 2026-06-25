from __future__ import annotations

import cocotb
from cocotb.triggers import RisingEdge, Timer

from cocotb_helpers import start_clock_and_reset


TOP_K = 4


async def _reset(dut) -> None:
    dut.update_valid.value = 0
    dut.update_side.value = 0
    dut.update_subtract.value = 0
    dut.update_price.value = 0
    dut.update_qty.value = 0
    dut.rsp_ready.value = 1
    await start_clock_and_reset(dut)


async def _update(dut, *, side: int, subtract: int, price: int, qty: int) -> int:
    dut.update_valid.value = 1
    dut.update_side.value = side
    dut.update_subtract.value = subtract
    dut.update_price.value = price
    dut.update_qty.value = qty
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.update_valid.value = 0
    assert int(dut.rsp_valid.value) == 1
    return int(dut.rsp_error.value)


def _levels(price_word: int, qty_word: int) -> list[tuple[int, int]]:
    pairs = []
    for rank in range(TOP_K):
        price = (price_word >> (rank * 32)) & 0xFFFFFFFF
        qty = (qty_word >> (rank * 32)) & 0xFFFFFFFF
        if price or qty:
            pairs.append((price, qty))
    return pairs


@cocotb.test()
async def topk_outputs_sorted_bid_and_ask_levels(dut) -> None:
    await _reset(dut)
    assert await _update(dut, side=1, subtract=0, price=100, qty=10) == 0
    assert await _update(dut, side=1, subtract=0, price=101, qty=5) == 0
    assert await _update(dut, side=0, subtract=0, price=105, qty=8) == 0
    assert await _update(dut, side=0, subtract=0, price=104, qty=9) == 0

    bids = _levels(int(dut.bid_prices.value), int(dut.bid_qtys.value))
    asks = _levels(int(dut.ask_prices.value), int(dut.ask_qtys.value))
    assert bids[:2] == [(101, 5), (100, 10)]
    assert asks[:2] == [(104, 9), (105, 8)]

    assert await _update(dut, side=1, subtract=1, price=100, qty=4) == 0
    bids = _levels(int(dut.bid_prices.value), int(dut.bid_qtys.value))
    assert bids[:2] == [(101, 5), (100, 6)]

    assert await _update(dut, side=0, subtract=1, price=105, qty=9) == 3
    asks = _levels(int(dut.ask_prices.value), int(dut.ask_qtys.value))
    assert asks[:2] == [(104, 9), (105, 8)]


@cocotb.test()
async def response_holds_under_backpressure(dut) -> None:
    await _reset(dut)
    dut.rsp_ready.value = 0
    assert await _update(dut, side=1, subtract=0, price=100, qty=10) == 0
    held = (
        int(dut.rsp_error.value),
        int(dut.bid_prices.value),
        int(dut.bid_qtys.value),
    )
    for _ in range(3):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        assert int(dut.rsp_valid.value) == 1
        assert (int(dut.rsp_error.value), int(dut.bid_prices.value), int(dut.bid_qtys.value)) == held
