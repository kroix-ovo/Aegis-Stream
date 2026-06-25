"""Run cocotb scoreboards for the simulation-grade RTL modules."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import xml.etree.ElementTree as ET

from cocotb_tools.runner import get_runner


ROOT = Path(__file__).resolve().parents[2]
RTL = ROOT / "hardware" / "rtl"
COCOTB = ROOT / "hardware" / "cocotb"
BUILD = ROOT / "sim_build"


TESTS = {
    "parser": {
        "top": "itch_canonicalizer",
        "module": "test_itch_canonicalizer",
        "sources": ["aegis_stream_pkg.sv", "itch_canonicalizer.sv"],
    },
    "order": {
        "top": "order_ref_store",
        "module": "test_order_ref_store",
        "sources": ["aegis_stream_pkg.sv", "order_ref_store.sv"],
    },
    "telemetry": {
        "top": "latency_telemetry",
        "module": "test_latency_telemetry",
        "sources": ["aegis_stream_pkg.sv", "latency_telemetry.sv"],
    },
    "transport": {
        "top": "transport_seq_checker",
        "module": "test_transport_seq_checker",
        "sources": ["transport_seq_checker.sv"],
    },
    "packet-buffer": {
        "top": "itch_packet_buffer",
        "module": "test_itch_packet_buffer",
        "sources": ["itch_packet_buffer.sv"],
    },
    "price-level": {
        "top": "price_level_topk",
        "module": "test_price_level_topk",
        "sources": ["price_level_topk.sv"],
    },
    "feature-window": {
        "top": "feature_window_buffer",
        "module": "test_feature_window_buffer",
        "sources": ["feature_window_buffer.sv"],
    },
    "mixer": {
        "top": "temporal_mixer_int8",
        "module": "test_temporal_mixer_int8",
        "sources": ["temporal_mixer_int8.sv"],
    },
}


def run_one(name: str, *, sim: str, waves: bool) -> None:
    spec = TESTS[name]
    runner = get_runner(sim)
    build_dir = BUILD / name
    sources = [RTL / source for source in spec["sources"]]
    build_args: list[str] = []
    if sim == "icarus":
        build_args.extend(["-g2012", "-DAEGIS_DISABLE_SVA"])

    runner.build(
        sources=sources,
        hdl_toplevel=str(spec["top"]),
        build_args=build_args,
        build_dir=build_dir,
        always=True,
        waves=waves,
    )
    results_xml = build_dir / "results.xml"
    runner.test(
        test_module=str(spec["module"]),
        hdl_toplevel=str(spec["top"]),
        hdl_toplevel_lang="verilog",
        build_dir=build_dir,
        test_dir=COCOTB,
        waves=waves,
        results_xml=str(results_xml),
    )
    results = ET.parse(results_xml).getroot()
    failures = results.findall(".//failure") + results.findall(".//error")
    if failures:
        raise SystemExit(f"{name} cocotb suite failed; see {results_xml}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("suite", choices=(*TESTS.keys(), "all"))
    args = parser.parse_args()

    sim = os.environ.get("SIM", "icarus")
    waves = os.environ.get("WAVES", "0") not in {"", "0", "false", "False"}
    suites = TESTS.keys() if args.suite == "all" else [args.suite]
    for suite in suites:
        run_one(suite, sim=sim, waves=waves)


if __name__ == "__main__":
    main()
