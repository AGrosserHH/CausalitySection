"""Runs the real DoWhy path through estimate_effect.

Every API test patches estimate_effect, so without this module nothing executes its body.
No database is needed.
"""
import numpy as np
import pandas as pd
from django.test import SimpleTestCase

from .services import analyze_time_series_graph, build_dot_graph, estimate_effect


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


class TimeSeriesWindowTests(SimpleTestCase):
    """Windows must be periods of time shared by all entities, not slices of rows."""

    @staticmethod
    def panel(entities, days):
        rng = np.random.default_rng(11)
        rows = []
        for entity in entities:
            a_values = rng.normal(size=days)
            for day in range(days):
                rows.append({
                    "timestamp": f"2024-01-{day + 1:02d}",
                    "entity": entity,
                    "A": a_values[day],
                    # B follows A with a one-step delay inside each entity.
                    "B": a_values[day - 1] if day else 0.0,
                })
        return pd.DataFrame(rows)

    def test_windows_split_time_not_entities(self):
        result = analyze_time_series_graph(
            self.panel(["u1", "u2", "u3"], 12), [("A", "B")],
            time_column="timestamp", entity_column="entity", window_count=3, max_lag=2,
        )
        windows = result["dynamic_graphs"]
        self.assertEqual([(w["start"][:10], w["end"][:10]) for w in windows], [
            ("2024-01-01", "2024-01-04"), ("2024-01-05", "2024-01-08"), ("2024-01-09", "2024-01-12"),
        ])
        self.assertEqual(result["window_count"], 3)

    def test_lag_uses_history_from_before_the_window(self):
        result = analyze_time_series_graph(
            self.panel(["u1", "u2"], 9), [("A", "B")],
            time_column="timestamp", entity_column="entity", window_count=3, max_lag=2,
        )
        first, *later = [window["edges"][0] for window in result["dynamic_graphs"]]
        # Three timestamps per window. The first window has no earlier source
        # value for its first target, leaving two pairs: too few to correlate.
        self.assertIsNone(first["best_lag"])
        # Later windows pair their first target with the previous window's
        # source value, keeping all three pairs and the exact one-step relation.
        for edge in later:
            self.assertEqual(edge["best_lag"], 1)
            self.assertAlmostEqual(edge["strength"], 1.0, places=4)

    def test_unparsable_timestamps_are_left_out(self):
        frame = self.panel(["u1", "u2"], 12)
        frame.loc[5, "timestamp"] = "not a date"
        result = analyze_time_series_graph(
            frame, [("A", "B")],
            time_column="timestamp", entity_column="entity", window_count=3, max_lag=1,
        )
        rows = next(d for d in result["diagnostics"] if d["label"] == "Rows analysed")
        self.assertEqual(rows["value"], 23)
        self.assertEqual(result["window_count"], 3)

    def test_fewer_timestamps_than_windows_is_reported(self):
        result = analyze_time_series_graph(
            self.panel(["u1", "u2", "u3", "u4"], 3), [("A", "B")],
            time_column="timestamp", entity_column="entity", window_count=4, max_lag=1,
        )
        self.assertEqual(result["window_count"], 3)
        self.assertEqual(result["requested_window_count"], 4)
        windows = next(d for d in result["diagnostics"] if d["label"] == "Windows")
        self.assertEqual(windows["status"], "watch")
