# Interfaces

## Python APIs

### ITCH Parser

```python
from aegis_stream.itch import parse_messages

events = parse_messages(payload)
word = events[0].to_word256()
```

Supported messages:

- `A`: Add order
- `F`: Add order with MPID attribution
- `E`: Execute
- `C`: Execute with price
- `X`: Cancel
- `D`: Delete
- `U`: Replace
- `P`: Non-cross trade

### Book State

```python
from aegis_stream.book import OrderBookShard

book = OrderBookShard(symbol="AEGIS", top_k=32)
snapshot = book.apply_event(events[0])
```

Strict mode rejects duplicate live order references, missing deletes, and
over-cancels. That is deliberate: silent correction would hide the same class of
state corruption that the hardware must never allow.

### End-to-End Replay

```python
from aegis_stream.itch import demo_payload
from aegis_stream.pipeline import run_replay

result = run_replay(demo_payload(), window=128, feature_count=64)
print(result.to_jsonable())
```

## RTL Interfaces

### Canonicalizer Input

The starter canonicalizer accepts one aligned ITCH message at byte zero of a
512-bit payload beat:

```systemverilog
input  logic [511:0] s_payload_tdata;
input  logic [63:0]  s_payload_tkeep;
input  logic         s_payload_tvalid;
output logic         s_payload_tready;
input  logic         s_payload_tlast;
input  logic [63:0]  s_payload_timestamp_ns;
```

### Canonicalizer Output

```systemverilog
output logic [255:0] m_event_tdata;
output logic         m_event_tvalid;
input  logic         m_event_tready;
output logic [7:0]   m_error;
```

The output word uses `aegis_stream_pkg::aegis_event_t`.

### Order-Reference Store

`hardware/rtl/order_ref_store.sv` is the first synthesizable lifecycle store for
order-reference state. It is intentionally small and fully searchable for early
simulation, but it keeps the mutation semantics that the later banked/HBM design
must preserve.

```systemverilog
input  logic        req_valid;
output logic        req_ready;
input  logic [2:0]  req_op;           // insert, exec, cancel, delete, replace
input  logic [63:0] req_order_ref;
input  logic [63:0] req_new_order_ref;
input  logic [15:0] req_symbol;
input  logic        req_side;
input  logic [31:0] req_price;
input  logic [31:0] req_qty;

output logic        rsp_valid;
input  logic        rsp_ready;
output logic        rsp_hit;
output logic [15:0] rsp_symbol;
output logic        rsp_side;
output logic [31:0] rsp_price;
output logic [31:0] rsp_qty;
output logic [7:0]  rsp_err;
```

Current response error codes:

| Code | Meaning |
|---:|---|
| 0 | OK |
| 1 | Duplicate insert |
| 2 | Missing order |
| 3 | Invalid or excessive quantity |
| 4 | Store full |
| 5 | Replace target already exists |
| 6 | Invalid operation |

## Verification Contract

Every future RTL module should have:

- A ready/valid stability assertion.
- A directed test for each supported event type.
- A randomized backpressure test.
- A scoreboard that compares against `src/aegis_stream`.
- A latency or cycle-count measurement path that feeds telemetry.

Run current hardware checks with:

```bash
make lint-rtl
make sim-rtl
```
