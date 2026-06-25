`timescale 1ns/1ps

module feature_window_buffer #(
  parameter int FEATURE_COUNT = 64,
  parameter int FEATURE_W = 8,
  parameter int WINDOW = 8,
  parameter int INDEX_W = 3
) (
  input  logic                              clk,
  input  logic                              rst_n,

  input  logic                              feature_valid,
  output logic                              feature_ready,
  input  logic [FEATURE_COUNT*FEATURE_W-1:0] feature_tdata,

  input  logic [INDEX_W-1:0]                read_age,
  output logic [FEATURE_COUNT*FEATURE_W-1:0] read_tdata,
  output logic [FEATURE_COUNT*FEATURE_W-1:0] latest_tdata,
  output logic [31:0]                       rows_seen,
  output logic [INDEX_W-1:0]                cursor
);
  logic [FEATURE_COUNT*FEATURE_W-1:0] rows_q [0:WINDOW-1];
  logic [31:0] count_q;
  logic [INDEX_W-1:0] latest_idx;
  logic [INDEX_W-1:0] read_idx;
  logic read_valid;

  assign feature_ready = 1'b1;
  assign rows_seen = count_q;
  assign latest_idx = cursor - {{INDEX_W-1{1'b0}}, 1'b1};
  assign read_idx = latest_idx - read_age;
  assign read_valid = count_q != 32'd0 && {{(32-INDEX_W){1'b0}}, read_age} < count_q;

  always_comb begin
    latest_tdata = '0;
    read_tdata = '0;
    for (int i = 0; i < WINDOW; i++) begin
      if (count_q != 32'd0 && latest_idx == INDEX_W'(i)) begin
        latest_tdata = rows_q[i];
      end
      if (read_valid && read_idx == INDEX_W'(i)) begin
        read_tdata = rows_q[i];
      end
    end
  end

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      count_q <= 32'd0;
      cursor <= '0;
      for (int i = 0; i < WINDOW; i++) begin
        rows_q[i] <= '0;
      end
    end else if (feature_valid) begin
      rows_q[cursor] <= feature_tdata;
      cursor <= cursor == INDEX_W'(WINDOW - 1) ? '0 : cursor + {{INDEX_W-1{1'b0}}, 1'b1};
      if (count_q < WINDOW) begin
        count_q <= count_q + 32'd1;
      end
    end
  end
endmodule
