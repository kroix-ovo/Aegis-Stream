import unittest

from aegis_stream.benchmark import benchmark_payload
from aegis_stream.pipeline import stress_payload


class BenchmarkTests(unittest.TestCase):
    def test_benchmark_payload_reports_components(self) -> None:
        report = benchmark_payload(stress_payload(events=16, symbols=2), iterations=1, window=8)
        self.assertEqual(report["events"], 16)
        self.assertIn("events_per_second", report["parser"])
        self.assertEqual(report["book"]["mismatch_count"], 0)
        self.assertIn("latency_ns", report["feature"])
        self.assertIn("last_inference", report["model"])


if __name__ == "__main__":
    unittest.main()
