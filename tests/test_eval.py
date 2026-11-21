import unittest

from harness.tasks import load_task
from harness.trace import read_trace
from eval.metrics import metrics
from eval.stats import interval, margin, pass_at_k, pass_hat_k, spread


class EvaluationMathTests(unittest.TestCase):
    def test_reliability(self):
        self.assertAlmostEqual(pass_at_k(8, 6, 2), 0.9643, places=3)
        self.assertAlmostEqual(pass_hat_k(8, 6, 2), 0.5357, places=3)
        self.assertAlmostEqual(pass_hat_k(8, 6, 4), 0.2143, places=3)

    def test_slide_18_spreads(self):
        old = [61.0, 63.5, 59.5, 62.0, 64.5, 61.5, 62.5, 60.5, 63.0, 62.0]
        new = [63.5, 65.0, 62.5, 66.0, 64.5, 67.5, 65.0, 64.0, 66.5, 65.5]
        self.assertAlmostEqual(sum(old) / len(old), 62.0)
        self.assertAlmostEqual(sum(new) / len(new), 65.0)
        self.assertAlmostEqual(spread(old), 1.47, places=2)
        self.assertAlmostEqual(spread(new), 1.47, places=2)
        self.assertAlmostEqual(interval(new, old)[0], 3.0)

    def test_slide_19_interval(self):
        self.assertAlmostEqual(margin(1.5, 10, 1.5, 10), 1.31, places=2)
        width = margin(1.5, 10, 1.5, 10)
        self.assertAlmostEqual(3 - width, 1.69, places=2)
        self.assertAlmostEqual(3 + width, 4.31, places=2)
        wide = margin(6.0, 10, 6.0, 10)
        self.assertAlmostEqual(3 - wide, -2.3, places=1)
        self.assertAlmostEqual(3 + wide, 8.3, places=1)

    def test_slide_27_metrics(self):
        task = load_task("fixtures/traces7/s27.task.yaml")
        got = metrics(read_trace("fixtures/traces7/s27.jsonl"), task)
        self.assertEqual(got["step_count"], 3)
        self.assertAlmostEqual(got["precision"], 4 / 5)
        self.assertAlmostEqual(got["recall"], 1.0)
        self.assertEqual(got["repeats"], 1)
        self.assertEqual(got["orphans"], 1)


if __name__ == "__main__":
    unittest.main()
