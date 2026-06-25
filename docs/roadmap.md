# Roadmap

## Phase 0: Seed Repository

Status: complete in this repo.

- Preserve the supplied research artifacts.
- Add executable Python golden models.
- Add starter RTL contracts.
- Add tests and CI.

## Phase 1: Parser and Replay Hardening

- Add packet framing for MoldUDP64 and SoupBinTCP style replay captures.
- Add variable-length, cross-beat ITCH parsing in RTL.
- Add malformed-packet and gap accounting.
- Add cocotb tests using Python parser scoreboards.

## Phase 2: Book-State Engine

- Implement banked order-reference store.
- Add hot-cache plus HBM-simulation tiers.
- Implement top-K price-level engine.
- Prove local invariants with SVA/SymbiYosys where practical.

## Phase 3: Feature and Model Core

- Freeze the feature vector schema.
- Train a float baseline on public LOB data.
- Add int8 quantization-aware training.
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
