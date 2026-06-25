`timescale 1ns/1ps

module order_ref_store #(
  parameter int DEPTH = 64,
  parameter int INDEX_W = 6
) (
  input  logic        clk,
  input  logic        rst_n,

  input  logic        req_valid,
  output logic        req_ready,
  input  logic [2:0]  req_op,
  input  logic [63:0] req_order_ref,
  input  logic [63:0] req_new_order_ref,
  input  logic [15:0] req_symbol,
  input  logic        req_side,
  input  logic [31:0] req_price,
  input  logic [31:0] req_qty,

  output logic        rsp_valid,
  input  logic        rsp_ready,
  output logic        rsp_hit,
  output logic [15:0] rsp_symbol,
  output logic        rsp_side,
  output logic [31:0] rsp_price,
  output logic [31:0] rsp_qty,
  output logic [7:0]  rsp_err
);
  import aegis_stream_pkg::*;

  logic [DEPTH-1:0] valid_q;
  logic [63:0] order_ref_q [DEPTH];
  logic [15:0] symbol_q [DEPTH];
  logic        side_q [DEPTH];
  logic [31:0] price_q [DEPTH];
  logic [31:0] qty_q [DEPTH];

  logic hit;
  logic new_hit;
  logic free_hit;
  logic [INDEX_W-1:0] hit_idx;
  logic [INDEX_W-1:0] new_hit_idx;
  logic [INDEX_W-1:0] free_idx;
  logic fire_req;

  assign req_ready = !rsp_valid || rsp_ready;
  assign fire_req = req_valid && req_ready;

  always_comb begin
    hit = 1'b0;
    new_hit = 1'b0;
    free_hit = 1'b0;
    hit_idx = '0;
    new_hit_idx = '0;
    free_idx = '0;

    for (int i = 0; i < DEPTH; i++) begin
      if (valid_q[i] && order_ref_q[i] == req_order_ref && !hit) begin
        hit = 1'b1;
        hit_idx = INDEX_W'(i);
      end
      if (valid_q[i] && order_ref_q[i] == req_new_order_ref && !new_hit) begin
        new_hit = 1'b1;
        new_hit_idx = INDEX_W'(i);
      end
      if (!valid_q[i] && !free_hit) begin
        free_hit = 1'b1;
        free_idx = INDEX_W'(i);
      end
    end
  end

  task automatic emit_response(
    input logic        hit_i,
    input logic [15:0] symbol_i,
    input logic        side_i,
    input logic [31:0] price_i,
    input logic [31:0] qty_i,
    input logic [7:0]  err_i
  );
    rsp_valid <= 1'b1;
    rsp_hit <= hit_i;
    rsp_symbol <= symbol_i;
    rsp_side <= side_i;
    rsp_price <= price_i;
    rsp_qty <= qty_i;
    rsp_err <= err_i;
  endtask

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      valid_q <= '0;
      rsp_valid <= 1'b0;
      rsp_hit <= 1'b0;
      rsp_symbol <= '0;
      rsp_side <= 1'b0;
      rsp_price <= '0;
      rsp_qty <= '0;
      rsp_err <= 8'd0;
    end else begin
      if (rsp_valid && rsp_ready && !req_valid) begin
        rsp_valid <= 1'b0;
      end

      if (fire_req) begin
        unique case (req_op)
          AEGIS_ORD_INSERT: begin
            if (hit) begin
              emit_response(1'b1, symbol_q[hit_idx], side_q[hit_idx], price_q[hit_idx], qty_q[hit_idx], 8'd1);
            end else if (!free_hit || req_qty == 32'd0) begin
              emit_response(1'b0, req_symbol, req_side, req_price, req_qty, !free_hit ? 8'd4 : 8'd3);
            end else begin
              valid_q[free_idx] <= 1'b1;
              order_ref_q[free_idx] <= req_order_ref;
              symbol_q[free_idx] <= req_symbol;
              side_q[free_idx] <= req_side;
              price_q[free_idx] <= req_price;
              qty_q[free_idx] <= req_qty;
              emit_response(1'b1, req_symbol, req_side, req_price, req_qty, 8'd0);
            end
          end

          AEGIS_ORD_EXEC, AEGIS_ORD_CANCEL: begin
            if (!hit) begin
              emit_response(1'b0, '0, 1'b0, '0, '0, 8'd2);
            end else if (req_qty == 32'd0 || req_qty > qty_q[hit_idx]) begin
              emit_response(1'b1, symbol_q[hit_idx], side_q[hit_idx], price_q[hit_idx], qty_q[hit_idx], 8'd3);
            end else begin
              logic [31:0] next_qty;
              next_qty = qty_q[hit_idx] - req_qty;
              qty_q[hit_idx] <= next_qty;
              if (next_qty == 32'd0) begin
                valid_q[hit_idx] <= 1'b0;
              end
              emit_response(1'b1, symbol_q[hit_idx], side_q[hit_idx], price_q[hit_idx], next_qty, 8'd0);
            end
          end

          AEGIS_ORD_DELETE: begin
            if (!hit) begin
              emit_response(1'b0, '0, 1'b0, '0, '0, 8'd2);
            end else begin
              valid_q[hit_idx] <= 1'b0;
              emit_response(1'b1, symbol_q[hit_idx], side_q[hit_idx], price_q[hit_idx], qty_q[hit_idx], 8'd0);
            end
          end

          AEGIS_ORD_REPLACE: begin
            if (!hit) begin
              emit_response(1'b0, '0, 1'b0, '0, '0, 8'd2);
            end else if (new_hit) begin
              emit_response(1'b1, symbol_q[new_hit_idx], side_q[new_hit_idx], price_q[new_hit_idx], qty_q[new_hit_idx], 8'd5);
            end else if (req_qty == 32'd0) begin
              emit_response(1'b1, symbol_q[hit_idx], side_q[hit_idx], price_q[hit_idx], qty_q[hit_idx], 8'd3);
            end else begin
              order_ref_q[hit_idx] <= req_new_order_ref;
              price_q[hit_idx] <= req_price;
              qty_q[hit_idx] <= req_qty;
              emit_response(1'b1, symbol_q[hit_idx], side_q[hit_idx], req_price, req_qty, 8'd0);
            end
          end

          default: begin
            emit_response(1'b0, '0, 1'b0, '0, '0, 8'd6);
          end
        endcase
      end
    end
  end

`ifndef AEGIS_DISABLE_SVA
  property p_response_holds_under_backpressure;
    @(posedge clk) disable iff (!rst_n)
      rsp_valid && !rsp_ready |=> rsp_valid && $stable({rsp_hit, rsp_symbol, rsp_side, rsp_price, rsp_qty, rsp_err});
  endproperty
  assert property (p_response_holds_under_backpressure);
`endif
endmodule
