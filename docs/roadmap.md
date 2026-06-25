# Roadmap

## Phase 0: Seed Repository

Status: complete in this repo.

- Preserve the supplied research artifacts.
- Add executable Python golden models.
- Add starter RTL contracts.
- Add tests and CI.

## Phase 1: Parser and Replay Hardening

Status: software complete, RTL pending.

- Packet framing for MoldUDP64, SoupBinTCP-style replay captures, raw payloads,
  generated stress traces, and classic PCAP UDP payload extraction.
- Malformed-packet, malformed-message, duplicate sequence, and gap accounting in
  software replay telemetry.
- Hardened Python ITCH parser with explicit truncated, unsupported, and
  validation errors plus incremental cross-chunk parsing.
- Remaining FPGA work: variable-length, cross-beat ITCH parsing in RTL and
  cocotb tests using Python parser and transport scoreboards.

## Phase 2: Book-State Engine

- Software golden reference supports multi-symbol sharding, strict/non-strict
  modes, order-reference lifecycle checks, top-K signatures, and replay mismatch
  records.
- Implement banked RTL order-reference store.
- Add hot-cache plus HBM-simulation tiers.
- Implement top-K price-level RTL engine.
- Prove local invariants with SVA/SymbiYosys where practical.

## Phase 3: Feature and Model Core

- Feature vector schema remains 64 signed int8 values by default.
- Software path includes float inference, fixed-point int8 inference,
  deterministic exported weights, and a dependency-free float baseline
  train/eval scaffold.
- Train a production float baseline on public LOB data.
- Add int8 quantization-aware training when a real dataset is selected.
- Port the temporal mixer into pipelined RTL or Chisel-generated SV.

## Phase 4: Board Bring-Up

- Integrate XRT/QDMA replay.
- Add timestamp-plane calibration.
- Capture stage telemetry from hardware.
- Report CDFs for parser, book, feature, model, and egress latency.

## Phase 5: Paper-Style Evaluation

- Compare finance-path metrics against software baselines.
- Compare sequence-core microbenchmarks against FPGA attention literature.
- Publish reproducible artifacts, diagrams, and a demo video.
