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

### Transport Replay

```python
from aegis_stream.transport import decode_transport

replay = decode_transport(capture_bytes, protocol="moldudp64")
payload = replay.payload
print(replay.counters.gaps, replay.counters.malformed_packets)
```

Supported software replay inputs:

- `raw`: concatenated ITCH messages.
- `moldudp64`: MoldUDP64 datagrams, optionally length-prefixed with u16/u32
  packet lengths for file captures.
- `soupbintcp`: two-byte length-prefixed SoupBinTCP-style stream frames where
  sequenced data frames carry ITCH payload bytes.
- `pcap`: classic PCAP Ethernet/IPv4/UDP payload extraction with `raw` or
  `moldudp64` UDP payloads.

### Book State

```python
from aegis_stream.book import MultiSymbolOrderBook, OrderBookShard

book = OrderBookShard(symbol="AEGIS", top_k=32)
snapshot = book.apply_event(events[0])

multi = MultiSymbolOrderBook(top_k=32, strict=True)
snapshot = multi.apply_event(events[0])
```

Strict mode rejects duplicate live order references, missing deletes, and
over-cancels. That is deliberate: silent correction would hide the same class of
state corruption that the hardware must never allow.

Non-strict mode records `BookIssue` entries instead of raising immediately,
which is useful for replay reports over imperfect captures. Snapshot comparison
helpers emit `ReplayMismatch` records for top-K depth mismatches.

### End-to-End Replay

```python
from aegis_stream.itch import demo_payload
from aegis_stream.pipeline import run_replay

result = run_replay(demo_payload(), window=128, feature_count=64)
print(result.to_jsonable())
```

CLI examples:

```bash
PYTHONPATH=src python3 -m aegis_stream.pipeline --demo --json
PYTHONPATH=src python3 -m aegis_stream.pipeline --stress 1024 --csv
PYTHONPATH=src python3 -m aegis_stream.pipeline --input capture.bin --format soupbintcp --non-strict --json
PYTHONPATH=src python3 -m aegis_stream.benchmark --stress 4096 --iterations 3 --json
```

### Model Reference

```python
from aegis_stream.model import FixedPointTemporalMixer, FloatTemporalMixer

float_model = FloatTemporalMixer()
fixed_model = FixedPointTemporalMixer()
float_result = float_model.predict(feature_window)
fixed_result = fixed_model.predict(feature_window)
```

The default fixed-point weights are loaded from the deterministic exported
fixture under `src/aegis_stream/data/`. The fallback float baseline trainer uses
only the Python standard library so public validation does not require PyTorch;
richer PyTorch training can consume the same exported feature matrices when
PyTorch is installed.

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
