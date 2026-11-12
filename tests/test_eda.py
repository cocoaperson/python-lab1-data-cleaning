"""Проверки требований на небольшом наборе с пустым месяцем и пропуском."""

import unittest

import numpy as np
import pandas as pd

from src.eda import (
    DATE,
    GROUP,
    TARGET,
    anomaly_rules,
    chart_groups,
    group_summary,
    mean_numpy,
    mean_python,
    median_pivot,
    time_summary,
)


class EdaTests(unittest.TestCase):
    def setUp(self):
        self.frame = pd.DataFrame(
            {
                TARGET: [0.0, 10.0, np.nan, -5.0],
                DATE: pd.to_datetime(
                    ["2020-01-01", "2020-01-02", "2020-03-01", "2020-03-02"], utc=True
                ),
                GROUP: ["A", "A", "B", "B"],
            }
        )

    def test_calendar_and_missing(self):
        result = time_summary(self.frame)
        self.assertEqual(len(result), 3)
        self.assertEqual(result.loc["2020-02", "count"], 0)
        self.assertTrue(np.isnan(result.loc["2020-02", "median_m"]))
        self.assertEqual(result.loc["2020-03", "count"], 2)
        self.assertEqual(result.loc["2020-03", "valid"], 1)
        pivot = median_pivot(self.frame, result.index)
        self.assertTrue(pivot["2020-02"].isna().all())
        self.assertEqual(pivot.loc["A", "2020-01"], 5)

    def test_rare_chart_only(self):
        frame = pd.DataFrame({GROUP: ["A"] * 99 + ["B"], TARGET: np.arange(100.0)})
        before = frame.copy(deep=True)
        labels, rare = chart_groups(frame, threshold=0.02)
        self.assertEqual(rare, ["B"])
        self.assertEqual(labels.iloc[-1], "прочие")
        self.assertIn("B", group_summary(frame).index)
        self.assertEqual(chart_groups(frame, threshold=0.01)[1], [])
        pd.testing.assert_frame_equal(frame, before)

    def test_rules_and_metric(self):
        values = pd.Series([0.0] * 8 + [-1.0, 100.0, np.nan])
        masks, table, bounds = anomaly_rules(values)
        self.assertEqual(bounds, (0.0, 0.0))
        self.assertEqual(len(masks["iqr"]), len(values))
        self.assertEqual(table["count"].tolist(), [2, 1])
        self.assertEqual(table["overlap"].tolist(), [1, 1])
        self.assertFalse(masks["iqr"].iloc[-1])
        self.assertFalse(masks["iqr"].iloc[0])
        x = values.dropna().to_numpy()
        self.assertAlmostEqual(mean_python(x), mean_numpy(x), places=12)


if __name__ == "__main__":
    unittest.main()
