"""Runs the real DoWhy path through estimate_effect.

Every API test patches estimate_effect, so without this module nothing executes its body.
No database is needed.
"""
import numpy as np
import pandas as pd
from django.test import SimpleTestCase

from .services import build_dot_graph, estimate_effect


class LegacyEstimateEffectTests(SimpleTestCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        rng = np.random.default_rng(7)
        n = 2000
        confounder = rng.normal(size=n)
        treatment = (confounder + rng.normal(size=n) > 0).astype(int)
        outcome = 2.0 * treatment + 1.5 * confounder + rng.normal(scale=0.5, size=n)
        cls.frame = pd.DataFrame({"T": treatment, "Y": outcome, "C": confounder})
        cls.dot_graph = build_dot_graph([("C", "T"), ("C", "Y"), ("T", "Y")])[0]

    def test_linear_regression_recovers_the_known_effect(self):
        result = estimate_effect(self.frame, "T", "Y", self.dot_graph, "backdoor.linear_regression")
        self.assertEqual(result["method_name"], "backdoor.linear_regression")
        self.assertIsInstance(result["estimated_effect"], float)
        # The generating coefficient is 2.0; the naive difference in means is about 3.7.
        self.assertAlmostEqual(result["estimated_effect"], 2.0, delta=0.1)

    def test_failure_is_explicit_and_names_the_cause(self):
        levels = np.where(self.frame["C"] > 0.5, "high", np.where(self.frame["C"] < -0.5, "low", "mid"))
        frame = self.frame.assign(T=levels)
        with self.assertRaises(ValueError) as caught:
            estimate_effect(frame, "T", "Y", self.dot_graph, "backdoor.propensity_score_matching")
        message = str(caught.exception)
        self.assertIn("backdoor.propensity_score_matching", message)
        self.assertIn("No other method or unadjusted mean difference was substituted", message)
        # The underlying reason has to reach the person running the analysis, not only the log.
        cause = caught.exception.__cause__
        self.assertIsNotNone(cause)
        first_line = (str(cause).strip().splitlines() or [type(cause).__name__])[0]
        self.assertIn(first_line[:60].rstrip("."), message)
