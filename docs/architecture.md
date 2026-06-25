# Architecture

Aegis-Stream is organized as a deterministic streaming pipeline with one
canonical event format between market-data parsing and book/model processing.

```mermaid
flowchart LR
    A["100 GbE CMAC or PCIe replay"] --> B["Transport decode and sequence check"]
    B --> C["ITCH canonicalizer"]
    C --> D["Shard scheduler by stock_locate"]
    D --> E["Order-reference store"]
    D --> F["Price-level book state"]
    E --> F
    F --> G["Feature-window engine"]
    G --> H["Quantized sequence core"]
    H --> I["Score, confidence, telemetry"]
    I --> J["PCIe MMIO, DMA, or UDP egress"]
    K["Timestamp plane"] --> B
    K --> I
```

## Data Contract

The canonical event is 256 bits:

| Bits | Field | Notes |
|---:|---|---|
| 255:248 | event type | Normalized Aegis event code |
| 247:232 | stock locate | Nasdaq stock-locate field |
| 231:168 | order reference | Existing or old order reference |
| 167:136 | price | ITCH integer price |
| 135:104 | shares | ITCH integer quantity |
| 103:96 | side flags | `1=bid`, `2=ask` |
| 95:32 | timestamp | Nanoseconds since midnight or aligned timestamp |
| 31:0 | misc | Tracking and match-number low bits |

`src/aegis_stream/itch.py` and `hardware/rtl/aegis_stream_pkg.sv` are kept in
lockstep for this format.

## Software Golden Path

The Python implementation is the reference model used to validate future RTL:

1. `transport.decode_transport` decodes raw, MoldUDP64, SoupBinTCP-style, and
   classic PCAP replay inputs while tracking sequence gaps and malformed
   capture counters.
2. `itch.parse_messages` and `ItchStreamDecoder` decode complete or
   cross-chunk ITCH messages into the canonical event contract.
3. `MultiSymbolOrderBook.apply_event` mutates exact order-reference and level
   state across sharded symbols.
4. `FeatureWindowEngine.update` emits a 64-feature int8 vector and rolling
   window.
5. `FloatTemporalMixer` and `FixedPointTemporalMixer` provide float and bit-true
   fixed-point model references.
6. `TelemetryRecorder` reports stage-wise replay latency summaries.

## RTL Simulation Path

The RTL path is simulation-grade and intentionally board-agnostic. It now
contains:

1. `itch_packet_buffer` for cross-beat ITCH message realignment.
2. `itch_canonicalizer` for aligned A/F/E/C/X/D/U/P canonical event packing.
3. `transport_seq_checker` for sequence, gap, duplicate, malformed, and packet
   counters.
4. `order_ref_store` for order lifecycle mutation checks.
5. `price_level_topk` for single-shard aggregate top-K price levels.
6. `feature_window_buffer` for 64-int8 feature-vector ring buffering.
7. `temporal_mixer_int8` for a fixed-point int8 mixer datapath MVP.

The remaining hardware steps are board or production-RTL work: compose these
modules into a deeper parser/book pipeline, replace small searchable structures
with banked BRAM/URAM/HBM designs, implement the full temporal lookback core,
and integrate vendor shell, DMA, timing, and telemetry paths.
