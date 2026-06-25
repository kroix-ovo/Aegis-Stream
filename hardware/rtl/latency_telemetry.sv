`timescale 1ns/1ps

import aegis_stream_pkg::*;

module latency_telemetry (
  input  logic        clk,
  input  logic        rst_n,
  input  logic [31:0] event_id,
  input  logic [63:0] timestamp_counter,

  input  logic        mark_ingress,
  input  logic        mark_parser,
  input  logic        mark_book,
  input  logic        mark_feature,
  input  logic        mark_model,

  output logic [351:0] telemetry_data,
  output logic         telemetry_valid,
  input  logic         telemetry_ready
);
  aegis_telemetry_t record_q;

  assign telemetry_data = record_q;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      record_q <= '0;
      telemetry_valid <= 1'b0;
    end else begin
      if (mark_ingress) begin
        record_q.ingress_ts <= timestamp_counter;
        record_q.event_id <= event_id;
      end
      if (mark_parser) begin
        record_q.parser_ts <= timestamp_counter;
      end
      if (mark_book) begin
        record_q.book_ts <= timestamp_counter;
      end
      if (mark_feature) begin
        record_q.feature_ts <= timestamp_counter;
      end
      if (mark_model) begin
        record_q.model_ts <= timestamp_counter;
        telemetry_valid <= 1'b1;
      end else if (telemetry_valid && telemetry_ready) begin
        telemetry_valid <= 1'b0;
      end
    end
  end

  property p_valid_holds_until_ready;
    @(posedge clk) disable iff (!rst_n)
      telemetry_valid && !telemetry_ready |=> telemetry_valid && $stable(record_q);
  endproperty
  assert property (p_valid_holds_until_ready);
endmodule
