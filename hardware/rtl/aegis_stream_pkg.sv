`timescale 1ns/1ps

package aegis_stream_pkg;
  /* verilator lint_off UNUSEDPARAM */
  localparam int AEGIS_EVENT_W = 256;
  localparam int AEGIS_TELEMETRY_W = 384;
  /* verilator lint_on UNUSEDPARAM */

  typedef enum logic [7:0] {
    AEGIS_EVT_NONE    = 8'd0,
    AEGIS_EVT_ADD     = 8'd1,
    AEGIS_EVT_EXEC    = 8'd2,
    AEGIS_EVT_CANCEL  = 8'd3,
    AEGIS_EVT_DELETE  = 8'd4,
    AEGIS_EVT_REPLACE = 8'd5,
    AEGIS_EVT_TRADE   = 8'd6
  } aegis_event_type_e;

  typedef enum logic [2:0] {
    AEGIS_ORD_INSERT  = 3'd0,
    AEGIS_ORD_EXEC    = 3'd1,
    AEGIS_ORD_CANCEL  = 3'd2,
    AEGIS_ORD_DELETE  = 3'd3,
    AEGIS_ORD_REPLACE = 3'd4
  } aegis_order_op_e;

  typedef struct packed {
    logic [7:0]  event_type;
    logic [15:0] stock_locate;
    logic [63:0] order_ref;
    logic [31:0] price;
    logic [31:0] shares;
    logic [7:0]  side_flags;
    logic [63:0] timestamp_ns;
    logic [31:0] misc;
  } aegis_event_t;

  typedef struct packed {
    logic [63:0] ingress_ts;
    logic [63:0] parser_ts;
    logic [63:0] book_ts;
    logic [63:0] feature_ts;
    logic [63:0] model_ts;
    logic [31:0] event_id;
    logic [31:0] flags;
  } aegis_telemetry_t;
endpackage
