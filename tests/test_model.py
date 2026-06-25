import unittest

from aegis_stream.model import (
    FixedPointTemporalMixer,
    FloatTemporalMixer,
    compare_float_fixed,
    evaluate_regression,
    load_default_weights,
    train_float_baseline,
)


class ModelTests(unittest.TestCase):
    def test_default_weight_fixture_is_deterministic(self) -> None:
        weights = load_default_weights()
        self.assertEqual(weights.feature_count, 64)
        self.assertEqual(weights.hidden, 16)
        self.assertEqual(weights.input_weights[0][0], 4)
        self.assertEqual(weights.output_weights[0], -4)

    def test_float_and_fixed_paths_are_bounded(self) -> None:
        window = [[(row + col) % 9 - 4 for col in range(64)] for row in range(8)]
        fixed = FixedPointTemporalMixer().predict(window)
        floated = FloatTemporalMixer().predict(window)
        comparison = compare_float_fixed(window)
        self.assertIn(fixed.action, {"BUY", "SELL", "HOLD"})
        self.assertIn(floated.action, {"BUY", "SELL", "HOLD"})
        self.assertLessEqual(comparison["score_abs_error_bps"], 20.0)

    def test_numpy_training_and_eval_scaffold(self) -> None:
        examples = [[0.0, 1.0], [1.0, 1.0], [2.0, 1.0], [3.0, 1.0]]
        labels = [0.0, 1.0, 2.0, 3.0]
        model = train_float_baseline(examples, labels, epochs=20, learning_rate=0.05)
        metrics = evaluate_regression(model, examples, labels)
        self.assertEqual(metrics["count"], 4.0)
        self.assertLess(metrics["mse"], 4.0)


if __name__ == "__main__":
    unittest.main()
