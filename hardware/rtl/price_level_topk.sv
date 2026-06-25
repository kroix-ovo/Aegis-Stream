`timescale 1ns/1ps

module price_level_topk #(
  parameter int LEVELS = 8,
  parameter int TOP_K = 4,
  parameter int INDEX_W = 3
) (
  input  logic        clk,
  input  logic        rst_n,

  input  logic        update_valid,
  output logic        update_ready,
  input  logic        update_side,       // 1 = bid, 0 = ask
  input  logic        update_subtract,
  input  logic [31:0] update_price,
  input  logic [31:0] update_qty,

  output logic        rsp_valid,
  input  logic        rsp_ready,
  output logic [7:0]  rsp_error,

  output logic [TOP_K*32-1:0] bid_prices,
  output logic [TOP_K*32-1:0] bid_qtys,
  output logic [TOP_K*32-1:0] ask_prices,
  output logic [TOP_K*32-1:0] ask_qtys
);
  logic [LEVELS-1:0] bid_valid_q;
  logic [LEVELS-1:0] ask_valid_q;
  logic [31:0] bid_price_q [0:LEVELS-1];
  logic [31:0] bid_qty_q [0:LEVELS-1];
  logic [31:0] ask_price_q [0:LEVELS-1];
  logic [31:0] ask_qty_q [0:LEVELS-1];

  logic fire_update;
  logic bid_hit;
  logic ask_hit;
  logic bid_free;
  logic ask_free;
  logic [INDEX_W-1:0] bid_hit_idx;
  logic [INDEX_W-1:0] ask_hit_idx;
  logic [INDEX_W-1:0] bid_free_idx;
  logic [INDEX_W-1:0] ask_free_idx;

  assign update_ready = !rsp_valid || rsp_ready;
  assign fire_update = update_valid && update_ready;

  always_comb begin
    bid_hit = 1'b0;
    ask_hit = 1'b0;
    bid_free = 1'b0;
    ask_free = 1'b0;
    bid_hit_idx = '0;
    ask_hit_idx = '0;
    bid_free_idx = '0;
    ask_free_idx = '0;

    for (int i = 0; i < LEVELS; i++) begin
      if (bid_valid_q[i] && bid_price_q[i] == update_price && !bid_hit) begin
        bid_hit = 1'b1;
        bid_hit_idx = INDEX_W'(i);
      end
      if (ask_valid_q[i] && ask_price_q[i] == update_price && !ask_hit) begin
        ask_hit = 1'b1;
        ask_hit_idx = INDEX_W'(i);
      end
      if (!bid_valid_q[i] && !bid_free) begin
        bid_free = 1'b1;
        bid_free_idx = INDEX_W'(i);
      end
      if (!ask_valid_q[i] && !ask_free) begin
        ask_free = 1'b1;
        ask_free_idx = INDEX_W'(i);
      end
    end
  end

  task automatic emit_response(input logic [7:0] error_i);
    rsp_valid <= 1'b1;
    rsp_error <= error_i;
  endtask

  task automatic apply_bid_update;
    if (update_qty == 32'd0) begin
      emit_response(8'd3);
    end else if (update_subtract) begin
      if (!bid_hit) begin
        emit_response(8'd2);
      end else if (update_qty > bid_qty_q[bid_hit_idx]) begin
        emit_response(8'd3);
      end else if (update_qty == bid_qty_q[bid_hit_idx]) begin
        bid_valid_q[bid_hit_idx] <= 1'b0;
        bid_qty_q[bid_hit_idx] <= 32'd0;
        emit_response(8'd0);
      end else begin
        bid_qty_q[bid_hit_idx] <= bid_qty_q[bid_hit_idx] - update_qty;
        emit_response(8'd0);
      end
    end else if (bid_hit) begin
      bid_qty_q[bid_hit_idx] <= bid_qty_q[bid_hit_idx] + update_qty;
      emit_response(8'd0);
    end else if (!bid_free) begin
      emit_response(8'd4);
    end else begin
      bid_valid_q[bid_free_idx] <= 1'b1;
      bid_price_q[bid_free_idx] <= update_price;
      bid_qty_q[bid_free_idx] <= update_qty;
      emit_response(8'd0);
    end
  endtask

  task automatic apply_ask_update;
    if (update_qty == 32'd0) begin
      emit_response(8'd3);
    end else if (update_subtract) begin
      if (!ask_hit) begin
        emit_response(8'd2);
      end else if (update_qty > ask_qty_q[ask_hit_idx]) begin
        emit_response(8'd3);
      end else if (update_qty == ask_qty_q[ask_hit_idx]) begin
        ask_valid_q[ask_hit_idx] <= 1'b0;
        ask_qty_q[ask_hit_idx] <= 32'd0;
        emit_response(8'd0);
      end else begin
        ask_qty_q[ask_hit_idx] <= ask_qty_q[ask_hit_idx] - update_qty;
        emit_response(8'd0);
      end
    end else if (ask_hit) begin
      ask_qty_q[ask_hit_idx] <= ask_qty_q[ask_hit_idx] + update_qty;
      emit_response(8'd0);
    end else if (!ask_free) begin
      emit_response(8'd4);
    end else begin
      ask_valid_q[ask_free_idx] <= 1'b1;
      ask_price_q[ask_free_idx] <= update_price;
      ask_qty_q[ask_free_idx] <= update_qty;
      emit_response(8'd0);
    end
  endtask

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      bid_valid_q <= '0;
      ask_valid_q <= '0;
      rsp_valid <= 1'b0;
      rsp_error <= 8'd0;
      for (int i = 0; i < LEVELS; i++) begin
        bid_price_q[i] <= 32'd0;
        bid_qty_q[i] <= 32'd0;
        ask_price_q[i] <= 32'd0;
        ask_qty_q[i] <= 32'd0;
      end
    end else begin
      if (rsp_valid && rsp_ready && !update_valid) begin
        rsp_valid <= 1'b0;
      end
      if (fire_update) begin
        if (update_side) begin
          apply_bid_update();
        end else begin
          apply_ask_update();
        end
      end
    end
  end

  always_comb begin
    logic [LEVELS-1:0] selected;
    bid_prices = '0;
    bid_qtys = '0;
    selected = '0;
    for (int rank = 0; rank < TOP_K; rank++) begin
      logic found;
      logic [INDEX_W-1:0] best_idx;
      found = 1'b0;
      best_idx = '0;
      for (int i = 0; i < LEVELS; i++) begin
        if (bid_valid_q[i] && !selected[i] && (!found || bid_price_q[i] > bid_price_q[best_idx])) begin
          found = 1'b1;
          best_idx = INDEX_W'(i);
        end
      end
      if (found) begin
        selected[best_idx] = 1'b1;
        bid_prices[rank*32 +: 32] = bid_price_q[best_idx];
        bid_qtys[rank*32 +: 32] = bid_qty_q[best_idx];
      end
    end

    ask_prices = '0;
    ask_qtys = '0;
    selected = '0;
    for (int rank = 0; rank < TOP_K; rank++) begin
      logic found;
      logic [INDEX_W-1:0] best_idx;
      found = 1'b0;
      best_idx = '0;
      for (int i = 0; i < LEVELS; i++) begin
        if (ask_valid_q[i] && !selected[i] && (!found || ask_price_q[i] < ask_price_q[best_idx])) begin
          found = 1'b1;
          best_idx = INDEX_W'(i);
        end
      end
      if (found) begin
        selected[best_idx] = 1'b1;
        ask_prices[rank*32 +: 32] = ask_price_q[best_idx];
        ask_qtys[rank*32 +: 32] = ask_qty_q[best_idx];
      end
    end
  end

`ifndef AEGIS_DISABLE_SVA
  property p_response_holds_under_backpressure;
    @(posedge clk) disable iff (!rst_n)
      rsp_valid && !rsp_ready |=> rsp_valid && $stable({rsp_error, bid_prices, bid_qtys, ask_prices, ask_qtys});
  endproperty
  assert property (p_response_holds_under_backpressure);
`endif
endmodule
