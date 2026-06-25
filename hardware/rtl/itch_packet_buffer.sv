`timescale 1ns/1ps

module itch_packet_buffer #(
  parameter int BUF_BYTES = 128
) (
  input  logic         clk,
  input  logic         rst_n,

  input  logic [511:0] s_payload_tdata,
  input  logic [63:0]  s_payload_tkeep,
  input  logic         s_payload_tvalid,
  output logic         s_payload_tready,
  input  logic         s_payload_tlast,
  input  logic [63:0]  s_payload_timestamp_ns,

  output logic [511:0] m_payload_tdata,
  output logic [63:0]  m_payload_tkeep,
  output logic         m_payload_tvalid,
  input  logic         m_payload_tready,
  output logic         m_payload_tlast,
  output logic [63:0]  m_payload_timestamp_ns,
  output logic [7:0]   m_error
);
  logic [7:0] buffer_q [0:BUF_BYTES-1];
  logic [7:0] count_q;
  logic       end_seen_q;
  logic [63:0] timestamp_q;

  logic [7:0] msg_len;
  logic [7:0] emit_len;
  logic       known_type;
  logic       complete_msg;
  logic       unsupported_msg;
  logic       truncated_msg;

  function automatic logic [7:0] message_length(input logic [7:0] msg_type);
    unique case (msg_type)
      8'h44: message_length = 8'd19;
      8'h58: message_length = 8'd23;
      8'h45: message_length = 8'd31;
      8'h55: message_length = 8'd35;
      8'h41, 8'h43: message_length = 8'd36;
      8'h46: message_length = 8'd40;
      8'h50: message_length = 8'd44;
      default: message_length = 8'd0;
    endcase
  endfunction

  assign msg_len = count_q == 8'd0 ? 8'd0 : message_length(buffer_q[0]);
  assign known_type = msg_len != 8'd0;
  assign complete_msg = known_type && (count_q >= msg_len);
  assign unsupported_msg = count_q != 8'd0 && !known_type;
  assign truncated_msg = end_seen_q && known_type && !complete_msg && count_q != 8'd0;
  assign m_payload_tvalid = complete_msg || unsupported_msg || truncated_msg;
  assign emit_len = complete_msg ? msg_len : unsupported_msg ? 8'd1 : count_q;
  assign s_payload_tready = !m_payload_tvalid && (count_q <= 8'(BUF_BYTES - 64));
  assign m_payload_tlast = 1'b1;
  assign m_payload_timestamp_ns = timestamp_q;
  assign m_error = unsupported_msg ? 8'd1 : truncated_msg ? 8'd2 : 8'd0;

  always_comb begin
    m_payload_tdata = '0;
    m_payload_tkeep = '0;
    for (int i = 0; i < 64; i++) begin
      if (i < emit_len) begin
        m_payload_tdata[511 - i*8 -: 8] = buffer_q[i];
        m_payload_tkeep[i] = 1'b1;
      end
    end
  end

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      count_q <= 8'd0;
      end_seen_q <= 1'b0;
      timestamp_q <= 64'd0;
      for (int i = 0; i < BUF_BYTES; i++) begin
        buffer_q[i] <= 8'd0;
      end
    end else if (m_payload_tvalid && m_payload_tready) begin
      int drop_count;
      drop_count = complete_msg ? int'(msg_len) : unsupported_msg ? 1 : int'(count_q);
      for (int i = 0; i < BUF_BYTES; i++) begin
        if (i + drop_count < BUF_BYTES) begin
          buffer_q[i] <= buffer_q[i + drop_count];
        end else begin
          buffer_q[i] <= 8'd0;
        end
      end
      count_q <= count_q - 8'(drop_count);
      if (int'(count_q) == drop_count) begin
        end_seen_q <= 1'b0;
      end
    end else if (s_payload_tvalid && s_payload_tready) begin
      int append_count;
      append_count = 0;
      if (count_q == 8'd0) begin
        timestamp_q <= s_payload_timestamp_ns;
      end
      for (int i = 0; i < 64; i++) begin
        if (s_payload_tkeep[i] && int'(count_q) + append_count < BUF_BYTES) begin
          buffer_q[int'(count_q) + append_count] <= s_payload_tdata[511 - i*8 -: 8];
          append_count = append_count + 1;
        end
      end
      count_q <= count_q + 8'(append_count);
      if (s_payload_tlast) begin
        end_seen_q <= 1'b1;
      end
    end
  end

`ifndef AEGIS_DISABLE_SVA
  property p_output_holds_under_backpressure;
    @(posedge clk) disable iff (!rst_n)
      m_payload_tvalid && !m_payload_tready |=> m_payload_tvalid && $stable({m_payload_tdata, m_payload_tkeep, m_error});
  endproperty
  assert property (p_output_holds_under_backpressure);
`endif
endmodule
