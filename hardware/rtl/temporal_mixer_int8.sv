`timescale 1ns/1ps

module temporal_mixer_int8 #(
  parameter int FEATURE_COUNT = 64
) (
  input  logic                         clk,
  input  logic                         rst_n,

  input  logic                         in_valid,
  output logic                         in_ready,
  input  logic [FEATURE_COUNT*8-1:0]   feature_tdata,
  input  logic [FEATURE_COUNT*8-1:0]   weight_tdata,
  input  logic signed [31:0]           bias,
  input  logic [3:0]                   output_shift,

  output logic                         out_valid,
  input  logic                         out_ready,
  output logic signed [31:0]           raw_logit,
  output logic signed [15:0]           score_bps
);
  assign in_ready = !out_valid || out_ready;

  function automatic logic signed [7:0] byte_at(input logic [FEATURE_COUNT*8-1:0] word, input int index);
    byte_at = word[index*8 +: 8];
  endfunction

  function automatic logic signed [15:0] clamp_score(input logic signed [31:0] value);
    if (value > 32'sd500) begin
      clamp_score = 16'sd500;
    end else if (value < -32'sd500) begin
      clamp_score = -16'sd500;
    end else begin
      clamp_score = value[15:0];
    end
  endfunction

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      out_valid <= 1'b0;
      raw_logit <= 32'sd0;
      score_bps <= 16'sd0;
    end else begin
      if (out_valid && out_ready && !in_valid) begin
        out_valid <= 1'b0;
      end
      if (in_valid && in_ready) begin
        logic signed [31:0] acc;
        logic signed [31:0] shifted;
        acc = bias;
        for (int i = 0; i < FEATURE_COUNT; i++) begin
          acc = acc + (32'(byte_at(feature_tdata, i)) * 32'(byte_at(weight_tdata, i)));
        end
        shifted = acc >>> output_shift;
        raw_logit <= acc;
        score_bps <= clamp_score(shifted);
        out_valid <= 1'b1;
      end
    end
  end

`ifndef AEGIS_DISABLE_SVA
  property p_output_holds_under_backpressure;
    @(posedge clk) disable iff (!rst_n)
      out_valid && !out_ready |=> out_valid && $stable({raw_logit, score_bps});
  endproperty
  assert property (p_output_holds_under_backpressure);
`endif
endmodule
