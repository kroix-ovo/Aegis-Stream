import unittest

from aegis_stream.features import FeatureWindowEngine
from aegis_stream.itch import demo_payload, parse_messages
from aegis_stream.pipeline import csv_report, run_replay, run_replay_capture, stress_payload
from aegis_stream.transport import encode_moldudp64_packet


class PipelineTests(unittest.TestCase):
    def test_demo_replay_runs_to_score(self) -> None:
        result = run_replay(demo_payload(), window=16)
        self.assertEqual(len(result.events), 7)
        self.assertEqual(len(result.snapshots), 7)
        self.assertEqual(len(result.vectors), 7)
        self.assertEqual(len(result.inferences), 7)
        self.assertIn(result.inferences[-1].action, {"BUY", "SELL", "HOLD"})
        self.assertEqual(result.telemetry_summary["events"], 7)
        self.assertEqual(result.to_jsonable()["book_mismatch_count"], 0)

    def test_feature_window_shape(self) -> None:
        result = run_replay(demo_payload(), window=8, feature_count=64)
        self.assertEqual(len(result.vectors[-1]), 64)

        engine = FeatureWindowEngine(window=4, feature_count=64)
        self.assertEqual(len(engine.matrix()), 4)
        self.assertEqual(len(engine.flattened()), 4 * 64)

        self.assertGreater(len(parse_messages(demo_payload())), 0)

    def test_transport_capture_replay(self) -> None:
        message = parse_messages(demo_payload())[0]
        packet = encode_moldudp64_packet([demo_payload()], sequence=1)
        result = run_replay_capture(packet, protocol="moldudp64", packet_framing="none")
        self.assertEqual(result.events[0].order_ref, message.order_ref)
        self.assertEqual(result.transport_summary["sequenced_payloads"], 1)

    def test_stress_trace_and_csv_report(self) -> None:
        payload = stress_payload(events=32, symbols=3)
        result = run_replay(payload, window=8)
        self.assertEqual(len(result.events), 32)
        rendered = csv_report(result.to_jsonable())
        self.assertIn("event_count,32", rendered)


if __name__ == "__main__":
    unittest.main()
