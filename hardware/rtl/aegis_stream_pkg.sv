package aegis_stream_pkg;
  localparam int AEGIS_EVENT_W = 256;

  typedef enum logic [7:0] {
    AEGIS_EVT_NONE    = 8'd0,
    AEGIS_EVT_ADD     = 8'd1,
    AEGIS_EVT_EXEC    = 8'd2,
    AEGIS_EVT_CANCEL  = 8'd3,
    AEGIS_EVT_DELETE  = 8'd4,
    AEGIS_EVT_REPLACE = 8'd5,
    AEGIS_EVT_TRADE   = 8'd6
  } aegis_event_type_e;

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
