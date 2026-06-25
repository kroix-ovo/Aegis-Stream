`timescale 1ns/1ps

module transport_seq_checker (
  input  logic        clk,
  input  logic        rst_n,
  input  logic        reset_counters,

  input  logic        packet_valid,
  output logic        packet_ready,
  input  logic [63:0] packet_sequence,
  input  logic [15:0] packet_message_count,
  input  logic        packet_malformed,

  output logic [63:0] expected_sequence,
  output logic [31:0] packets,
  output logic [31:0] payload_messages,
  output logic [31:0] gaps,
  output logic [31:0] duplicate_packets,
  output logic [31:0] malformed_packets,
  output logic [31:0] gap_messages
);
  logic seen_q;
  logic [63:0] packet_end_sequence;
  logic [31:0] gap_delta;

  assign packet_ready = 1'b1;
  assign packet_end_sequence = packet_sequence + {48'd0, packet_message_count};
  assign gap_delta = packet_sequence[31:0] - expected_sequence[31:0];

  always_ff @(posedge clk) begin
    if (!rst_n || reset_counters) begin
      seen_q <= 1'b0;
      expected_sequence <= 64'd0;
      packets <= 32'd0;
      payload_messages <= 32'd0;
      gaps <= 32'd0;
      duplicate_packets <= 32'd0;
      malformed_packets <= 32'd0;
      gap_messages <= 32'd0;
    end else if (packet_valid) begin
      packets <= packets + 32'd1;
      if (packet_malformed) begin
        malformed_packets <= malformed_packets + 32'd1;
      end else if (packet_message_count != 16'd0) begin
        payload_messages <= payload_messages + {16'd0, packet_message_count};
        if (!seen_q) begin
          seen_q <= 1'b1;
          expected_sequence <= packet_end_sequence;
        end else if (packet_sequence > expected_sequence) begin
          gaps <= gaps + 32'd1;
          gap_messages <= gap_messages + gap_delta;
          expected_sequence <= packet_end_sequence;
        end else if (packet_sequence < expected_sequence) begin
          duplicate_packets <= duplicate_packets + 32'd1;
          if (packet_end_sequence > expected_sequence) begin
            expected_sequence <= packet_end_sequence;
          end
        end else begin
          expected_sequence <= packet_end_sequence;
        end
      end
    end
  end

`ifndef AEGIS_DISABLE_SVA
  property p_ready_is_always_asserted;
    @(posedge clk) disable iff (!rst_n)
      packet_ready;
  endproperty
  assert property (p_ready_is_always_asserted);
`endif
endmodule
