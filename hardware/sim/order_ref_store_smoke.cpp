#include "Vorder_ref_store.h"
#include "verilated.h"

#include <cstdint>
#include <cstdlib>
#include <iostream>

namespace {

void tick(Vorder_ref_store& top) {
    top.clk = 0;
    top.eval();
    top.clk = 1;
    top.eval();
    top.clk = 0;
    top.eval();
}

void clear_req(Vorder_ref_store& top) {
    top.req_valid = 0;
    top.req_op = 0;
    top.req_order_ref = 0;
    top.req_new_order_ref = 0;
    top.req_symbol = 0;
    top.req_side = 0;
    top.req_price = 0;
    top.req_qty = 0;
}

void expect_eq(uint64_t actual, uint64_t expected, const char* name) {
    if (actual != expected) {
        std::cerr << name << ": expected 0x" << std::hex << expected
                  << " got 0x" << actual << std::dec << "\n";
        std::exit(1);
    }
}

void issue(Vorder_ref_store& top,
           uint8_t op,
           uint64_t order_ref,
           uint64_t new_order_ref,
           uint16_t symbol,
           bool side,
           uint32_t price,
           uint32_t qty) {
    top.req_valid = 1;
    top.req_op = op;
    top.req_order_ref = order_ref;
    top.req_new_order_ref = new_order_ref;
    top.req_symbol = symbol;
    top.req_side = side ? 1 : 0;
    top.req_price = price;
    top.req_qty = qty;
    tick(top);
    clear_req(top);
}

}  // namespace

int main(int argc, char** argv) {
    Verilated::commandArgs(argc, argv);
    Vorder_ref_store top;

    clear_req(top);
    top.rsp_ready = 1;
    top.rst_n = 0;
    tick(top);
    top.rst_n = 1;

    issue(top, 0, 1001, 0, 0x1234, true, 1000000, 300);
    expect_eq(top.rsp_valid, 1, "insert_valid");
    expect_eq(top.rsp_err, 0, "insert_err");
    expect_eq(top.rsp_hit, 1, "insert_hit");
    expect_eq(top.rsp_qty, 300, "insert_qty");

    issue(top, 2, 1001, 0, 0, false, 0, 75);
    expect_eq(top.rsp_err, 0, "cancel_err");
    expect_eq(top.rsp_qty, 225, "cancel_remaining");

    issue(top, 4, 1001, 2001, 0, false, 1000050, 200);
    expect_eq(top.rsp_err, 0, "replace_err");
    expect_eq(top.rsp_price, 1000050, "replace_price");
    expect_eq(top.rsp_qty, 200, "replace_qty");

    issue(top, 1, 2001, 0, 0, false, 0, 201);
    expect_eq(top.rsp_err, 3, "over_exec_err");
    expect_eq(top.rsp_qty, 200, "over_exec_preserves_qty");

    issue(top, 3, 2001, 0, 0, false, 0, 0);
    expect_eq(top.rsp_err, 0, "delete_err");
    expect_eq(top.rsp_qty, 200, "delete_prior_qty");

    issue(top, 3, 2001, 0, 0, false, 0, 0);
    expect_eq(top.rsp_err, 2, "missing_delete_err");

    std::cout << "order_ref_store smoke test passed\n";
    return 0;
}
