import unittest

from aegis_stream.features import FeatureWindowEngine
from aegis_stream.itch import demo_payload, parse_messages
from aegis_stream.pipeline import run_replay


class PipelineTests(unittest.TestCase):
    def test_demo_replay_runs_to_score(self) -> None:
        result = run_replay(demo_payload(), window=16)
        self.assertEqual(len(result.events), 7)
        self.assertEqual(len(result.snapshots), 7)
        self.assertEqual(len(result.vectors), 7)
        self.assertEqual(len(result.inferences), 7)
        self.assertIn(result.inferences[-1].action, {"BUY", "SELL", "HOLD"})
        self.assertEqual(result.telemetry_summary["events"], 7)

    def test_feature_window_shape(self) -> None:
        result = run_replay(demo_payload(), window=8, feature_count=64)
        self.assertEqual(len(result.vectors[-1]), 64)

        engine = FeatureWindowEngine(window=4, feature_count=64)
        self.assertEqual(len(engine.matrix()), 4)
        self.assertEqual(len(engine.flattened()), 4 * 64)

        self.assertGreater(len(parse_messages(demo_payload())), 0)


if __name__ == "__main__":
    unittest.main()
