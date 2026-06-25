`timescale 1ns/1ps

module itch_canonicalizer (
  input  logic         clk,
  input  logic         rst_n,

  input  logic [511:0] s_payload_tdata,
  input  logic [63:0]  s_payload_tkeep,
  input  logic         s_payload_tvalid,
  output logic         s_payload_tready,
  input  logic         s_payload_tlast,
  input  logic [63:0]  s_payload_timestamp_ns,

  output logic [aegis_stream_pkg::AEGIS_EVENT_W-1:0] m_event_tdata,
  output logic         m_event_tvalid,
  input  logic         m_event_tready,
  output logic [7:0]   m_error
);
  import aegis_stream_pkg::*;

  aegis_event_t event_q;
  logic         valid_q;
  logic [7:0]   error_q;
  logic [7:0]   decoded_type;
  logic [7:0]   next_error;

  assign s_payload_tready = !valid_q || m_event_tready;
  assign m_event_tdata = event_q;
  assign m_event_tvalid = valid_q;
  assign m_error = error_q;

  function automatic logic [15:0] be16(input logic [511:0] data, input int byte_idx);
    be16 = {data[511 - byte_idx*8 -: 8], data[511 - (byte_idx+1)*8 -: 8]};
  endfunction

  function automatic logic [31:0] be32(input logic [511:0] data, input int byte_idx);
    be32 = {
      data[511 - byte_idx*8 -: 8],
      data[511 - (byte_idx+1)*8 -: 8],
      data[511 - (byte_idx+2)*8 -: 8],
      data[511 - (byte_idx+3)*8 -: 8]
    };
  endfunction

  function automatic logic [63:0] be64(input logic [511:0] data, input int byte_idx);
    be64 = {
      data[511 - byte_idx*8 -: 8],
      data[511 - (byte_idx+1)*8 -: 8],
      data[511 - (byte_idx+2)*8 -: 8],
      data[511 - (byte_idx+3)*8 -: 8],
      data[511 - (byte_idx+4)*8 -: 8],
      data[511 - (byte_idx+5)*8 -: 8],
      data[511 - (byte_idx+6)*8 -: 8],
      data[511 - (byte_idx+7)*8 -: 8]
    };
  endfunction

  function automatic logic [63:0] be48_to_64(input logic [511:0] data, input int byte_idx);
    be48_to_64 = {
      16'd0,
      data[511 - byte_idx*8 -: 8],
      data[511 - (byte_idx+1)*8 -: 8],
      data[511 - (byte_idx+2)*8 -: 8],
      data[511 - (byte_idx+3)*8 -: 8],
      data[511 - (byte_idx+4)*8 -: 8],
      data[511 - (byte_idx+5)*8 -: 8]
    };
  endfunction

  function automatic aegis_event_t decode_aligned(input logic [511:0] data, input logic [63:0] arrival_ts);
    aegis_event_t decoded;
    logic [7:0] msg_type;
    decoded = '0;
    msg_type = data[511 -: 8];
    decoded.stock_locate = be16(data, 1);
    decoded.timestamp_ns = be48_to_64(data, 5);
    decoded.misc[31:16] = be16(data, 3);

    unique case (msg_type)
      8'h41, 8'h46: begin
        decoded.event_type = AEGIS_EVT_ADD;
        decoded.order_ref = be64(data, 11);
        decoded.side_flags = (data[511 - 19*8 -: 8] == 8'h42) ? 8'd1 : 8'd2;
        decoded.shares = be32(data, 20);
        decoded.price = be32(data, 32);
      end
      8'h45: begin
        decoded.event_type = AEGIS_EVT_EXEC;
        decoded.order_ref = be64(data, 11);
        decoded.shares = be32(data, 19);
        decoded.misc[15:0] = be16(data, 29);
      end
      8'h58: begin
        decoded.event_type = AEGIS_EVT_CANCEL;
        decoded.order_ref = be64(data, 11);
        decoded.shares = be32(data, 19);
      end
      8'h44: begin
        decoded.event_type = AEGIS_EVT_DELETE;
        decoded.order_ref = be64(data, 11);
      end
      8'h55: begin
        decoded.event_type = AEGIS_EVT_REPLACE;
        decoded.order_ref = be64(data, 11);
        decoded.shares = be32(data, 27);
        decoded.price = be32(data, 31);
      end
      8'h50: begin
        decoded.event_type = AEGIS_EVT_TRADE;
        decoded.order_ref = be64(data, 11);
        decoded.side_flags = (data[511 - 19*8 -: 8] == 8'h42) ? 8'd1 : 8'd2;
        decoded.shares = be32(data, 20);
        decoded.price = be32(data, 32);
      end
      default: begin
        decoded.event_type = AEGIS_EVT_NONE;
        decoded.timestamp_ns = arrival_ts;
      end
    endcase
    return decoded;
  endfunction

  function automatic logic [7:0] aligned_error(input logic [7:0] msg_type, input logic [39:0] keep, input logic last);
    unique case (msg_type)
      8'h44: aligned_error = (keep[18:0] != 19'h7ffff) ? 8'd2 : 8'd0;
      8'h58: aligned_error = (keep[22:0] != 23'h7fffff) ? 8'd2 : 8'd0;
      8'h45: aligned_error = (keep[30:0] != 31'h7fffffff) ? 8'd2 : 8'd0;
      8'h41: aligned_error = (keep[35:0] != 36'hfffffffff) ? 8'd2 : 8'd0;
      8'h55, 8'h43: aligned_error = (keep[35:0] != 36'hfffffffff) ? 8'd2 : 8'd0;
      8'h46, 8'h50: aligned_error = (keep[39:0] != 40'hffffffffff) ? 8'd2 : 8'd0;
      default: aligned_error = 8'd1;
    endcase
    if (!last) begin
      aligned_error = 8'd3;
    end
  endfunction

  always_comb begin
    unique case (s_payload_tdata[511 -: 8])
      8'h41, 8'h46: decoded_type = AEGIS_EVT_ADD;
      8'h45: decoded_type = AEGIS_EVT_EXEC;
      8'h58: decoded_type = AEGIS_EVT_CANCEL;
      8'h44: decoded_type = AEGIS_EVT_DELETE;
      8'h55: decoded_type = AEGIS_EVT_REPLACE;
      8'h50: decoded_type = AEGIS_EVT_TRADE;
      default: decoded_type = AEGIS_EVT_NONE;
    endcase
    next_error = aligned_error(s_payload_tdata[511 -: 8], s_payload_tkeep[39:0], s_payload_tlast);
    if (!s_payload_tvalid) begin
      next_error = 8'd0;
    end else if (decoded_type == AEGIS_EVT_NONE) begin
      next_error = 8'd1;
    end else if (|s_payload_tkeep[63:40]) begin
      next_error = 8'd4;
    end
  end

  always_ff @(posedge clk) begin
    if (!rst_n) begin
      event_q <= '0;
      valid_q <= 1'b0;
      error_q <= 8'd0;
    end else if (s_payload_tready) begin
      valid_q <= s_payload_tvalid;
      event_q <= decode_aligned(s_payload_tdata, s_payload_timestamp_ns);
      error_q <= next_error;
    end
  end

  property p_hold_when_backpressured;
    @(posedge clk) disable iff (!rst_n)
      valid_q && !m_event_tready |=> valid_q && $stable(event_q);
  endproperty
  assert property (p_hold_when_backpressured);
endmodule
