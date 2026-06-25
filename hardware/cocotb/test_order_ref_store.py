from __future__ import annotations

import cocotb
from cocotb.triggers import RisingEdge, Timer

from aegis_stream.book import OrderBookShard
from aegis_stream.itch import encode_add, encode_cancel, encode_delete, encode_execute, encode_replace, parse_messages

from cocotb_helpers import start_clock_and_reset


INSERT = 0
EXEC = 1
CANCEL = 2
DELETE = 3
REPLACE = 4


async def _reset(dut) -> None:
    dut.req_valid.value = 0
    dut.req_op.value = 0
    dut.req_order_ref.value = 0
    dut.req_new_order_ref.value = 0
    dut.req_symbol.value = 0
    dut.req_side.value = 0
    dut.req_price.value = 0
    dut.req_qty.value = 0
    dut.rsp_ready.value = 1
    await start_clock_and_reset(dut)


async def _issue(
    dut,
    op: int,
    order_ref: int,
    *,
    new_order_ref: int = 0,
    symbol: int = 7,
    side: int = 1,
    price: int = 0,
    qty: int = 0,
) -> dict[str, int]:
    dut.req_valid.value = 1
    dut.req_op.value = op
    dut.req_order_ref.value = order_ref
    dut.req_new_order_ref.value = new_order_ref
    dut.req_symbol.value = symbol
    dut.req_side.value = side
    dut.req_price.value = price
    dut.req_qty.value = qty
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    dut.req_valid.value = 0
    assert int(dut.rsp_valid.value) == 1
    return {
        "hit": int(dut.rsp_hit.value),
        "symbol": int(dut.rsp_symbol.value),
        "side": int(dut.rsp_side.value),
        "price": int(dut.rsp_price.value),
        "qty": int(dut.rsp_qty.value),
        "err": int(dut.rsp_err.value),
    }


@cocotb.test()
async def lifecycle_matches_software_book_for_valid_mutations(dut) -> None:
    await _reset(dut)
    book = OrderBookShard(symbol="LOCATE-7", top_k=4)

    add = parse_messages(
        encode_add(
            order_ref=1001,
            side="B",
            shares=300,
            stock="AEGIS",
            price=1_000_000,
            timestamp_ns=1,
            stock_locate=7,
        )
    )[0]
    snapshot = book.apply_event(add)
    rsp = await _issue(dut, INSERT, 1001, symbol=7, side=1, price=1_000_000, qty=300)
    assert rsp == {"hit": 1, "symbol": 7, "side": 1, "price": 1_000_000, "qty": 300, "err": 0}
    assert snapshot.best_bid.shares == rsp["qty"]

    cancel = parse_messages(encode_cancel(order_ref=1001, shares=75, timestamp_ns=2, stock_locate=7))[0]
    snapshot = book.apply_event(cancel)
    rsp = await _issue(dut, CANCEL, 1001, qty=75)
    assert rsp["err"] == 0
    assert rsp["qty"] == snapshot.best_bid.shares == 225

    replace = parse_messages(
        encode_replace(
            old_order_ref=1001,
            new_order_ref=2001,
            shares=150,
            price=1_000_050,
            timestamp_ns=3,
            stock_locate=7,
        )
    )[0]
    snapshot = book.apply_event(replace)
    rsp = await _issue(dut, REPLACE, 1001, new_order_ref=2001, price=1_000_050, qty=150)
    assert rsp["err"] == 0
    assert rsp["price"] == snapshot.best_bid.price == 1_000_050
    assert rsp["qty"] == snapshot.best_bid.shares == 150

    execute = parse_messages(encode_execute(order_ref=2001, shares=150, match_number=10, timestamp_ns=4, stock_locate=7))[0]
    snapshot = book.apply_event(execute)
    rsp = await _issue(dut, EXEC, 2001, qty=150)
    assert rsp["err"] == 0
    assert rsp["qty"] == 0
    assert snapshot.best_bid is None


@cocotb.test()
async def edge_cases_return_deterministic_error_codes(dut) -> None:
    await _reset(dut)

    assert (await _issue(dut, DELETE, 404))["err"] == 2
    assert (await _issue(dut, INSERT, 10, price=100, qty=100))["err"] == 0
    duplicate = await _issue(dut, INSERT, 10, price=100, qty=100)
    assert duplicate["err"] == 1
    assert duplicate["qty"] == 100

    over_exec = await _issue(dut, EXEC, 10, qty=101)
    assert over_exec["err"] == 3
    assert over_exec["qty"] == 100

    assert (await _issue(dut, INSERT, 20, price=101, qty=50))["err"] == 0
    duplicate_target = await _issue(dut, REPLACE, 10, new_order_ref=20, price=102, qty=60)
    assert duplicate_target["err"] == 5

    assert (await _issue(dut, CANCEL, 10, qty=100))["err"] == 0
    assert (await _issue(dut, DELETE, 10))["err"] == 2


@cocotb.test()
async def response_holds_under_backpressure(dut) -> None:
    await _reset(dut)
    dut.rsp_ready.value = 0

    rsp = await _issue(dut, INSERT, 77, price=1_000, qty=10)
    assert rsp["err"] == 0
    held = (
        int(dut.rsp_hit.value),
        int(dut.rsp_symbol.value),
        int(dut.rsp_side.value),
        int(dut.rsp_price.value),
        int(dut.rsp_qty.value),
        int(dut.rsp_err.value),
    )

    for _ in range(3):
        await RisingEdge(dut.clk)
        await Timer(1, unit="ns")
        assert int(dut.rsp_valid.value) == 1
        assert (
            int(dut.rsp_hit.value),
            int(dut.rsp_symbol.value),
            int(dut.rsp_side.value),
            int(dut.rsp_price.value),
            int(dut.rsp_qty.value),
            int(dut.rsp_err.value),
        ) == held
        assert int(dut.req_ready.value) == 0

    dut.rsp_ready.value = 1
    await RisingEdge(dut.clk)
    await Timer(1, unit="ns")
    assert int(dut.rsp_valid.value) == 0
