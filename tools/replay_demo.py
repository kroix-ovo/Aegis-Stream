#!/usr/bin/env python3
"""Run the built-in Aegis-Stream replay trace."""

from aegis_stream.pipeline import main


if __name__ == "__main__":
    raise SystemExit(main(["--demo", "--json"]))
