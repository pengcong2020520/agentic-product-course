import json
from pathlib import Path
import tempfile
import unittest

from tests._support import assert_success, run_cli, write_jsonl
from s05_agreement.code import verdict


class QualityReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.agreement = {
            "annotators": ["a", "b"], "sample": 12, "usable": 10, "both_relevant": 8,
            "undetermined": {"a": 1, "b": 2}, "needs_review": 99,
            "patches": [{"annotator": "a", "gene": "g17_risk", "path": "patches/chunk.jsonl", "applied": 7}],
            "genes": {
                "relevant": {"pairwise_kappa": {"a-b": 0.6}, "fleiss_kappa": 0.1},
                "g4_investment": {"pairwise_kappa": {"a-b": 0.4}},
                "g16_severity": {"pairwise_kappa": {"a-b": 0.399}},
                "g8_intensity": {"pairwise_kappa": {"a-b": 0.7}},
                "g17_risk": {"pairwise": {"a-b": {"mean_label_kappa": 0.55, "mean_jaccard": 0.99}}},
                "g12_competitor": {"pairwise": {"a-b": {"mean_label_kappa": None}}},
                "g13_expected": {"agent_expectation_count": {"a": 3, "b": 4}},
            },
        }

    def generate(self, rows, *, defaults=False):
        agreement = self.root / "data/double/report/agreement.json"
        agreement.parent.mkdir(parents=True)
        agreement.write_text(json.dumps(self.agreement, ensure_ascii=False), encoding="utf-8")
        final = self.root / "data/labeled/genome-final.jsonl"
        write_jsonl(final, rows)
        if defaults:
            out = self.root / "data/reports/quality-report.md"
            result = run_cli("s05_agreement/code.py", "quality", cwd=self.root)
        else:
            out = self.root / "reports/quality.md"
            result = run_cli("s05_agreement/code.py", "quality", "--agreement", agreement,
                             "--final", final, "--out", out, cwd=self.root)
        assert_success(self, result)
        return out.read_text(encoding="utf-8"), result.stdout

    def test_report_metrics_review_ratio_and_no_source_text(self):
        comment = "评论原文哨兵Q4X9"
        before_text = "裁决前文本哨兵A3V8"
        after_text = "Agent 应当自由文本哨兵B7W5"
        rows = [
            {"id": "changed", "text": comment, "needs_review": ["g16_severity"],
             "labels": {"g16_severity": "p0", "g13_expected": after_text},
             "review": {"decided": True, "before": {"g16_severity": "p1", "g13_expected": before_text}}},
            {"id": "unchanged", "labels": {"g16_severity": "p1"}, "needs_review": ["g16_severity"],
             "review": {"decided": True, "before": {"g16_severity": "p1"}}},
            {"id": "pending", "needs_review": ["relevant", "g16_severity"],
             "labels": {"relevant": "yes"}, "review": {"decided": False, "before": {"relevant": "off_topic"}}},
            {"id": "pending-no-review", "needs_review": ["relevant"]},
            {"id": "clean", "needs_review": []},
        ]
        report, stdout = self.generate(rows)
        for expected in (
            "| sample | 12 |", "| usable | 10 |", "| both_relevant | 8 |", "| a | 1 |", "| b | 2 |",
            "| a | g17_risk | patches/chunk.jsonl | 7 |",
            "| relevant | a-b | 两两 κ | 0.600 | 合格 |",
            "| g4_investment | a-b | 两两 κ | 0.400 | 需修订定义 |",
            "| g16_severity | a-b | 两两 κ | 0.399 | 需重写定义 |",
            "| g8_intensity | a-b | 加权 κ | 0.700 | 合格 |",
            "| g17_risk | a-b | 平均标签 κ | 0.550 | 需修订定义 |",
            "| g12_competitor | a-b | 平均标签 κ | — | 没能判定 |",
            "| g13_expected | a | Agent 应当条数 | 3 | 不计算 κ |",
            "| g13_expected | b | Agent 应当条数 | 4 | 不计算 κ |",
            "待裁决：2 条", "已裁决：2 条", "裁决改动主标注：1 条", "裁决改动比例：50.0%（1/2）",
        ):
            with self.subTest(expected=expected):
                self.assertIn(expected, report)
        for private in (comment, before_text, after_text):
            self.assertNotIn(private, report + stdout)

    def test_defaults_support_legacy_agreement_and_no_decisions(self):
        del self.agreement["patches"]
        report, _ = self.generate([], defaults=True)
        self.assertIn("补丁数量：0", report)
        self.assertIn("待裁决：0 条", report)
        self.assertIn("已裁决：0 条", report)
        self.assertIn("裁决改动主标注：0 条", report)
        self.assertIn("裁决改动比例：没能判定（已裁决为 0）（0/0）", report)

    def test_three_annotators_report_each_pair_not_fleiss(self):
        self.agreement["annotators"].append("c")
        self.agreement["undetermined"]["c"] = 0
        self.agreement["genes"]["relevant"] = {
            "pairwise_kappa": {"a-b": 0.6, "a-c": 0.4, "b-c": 0.2}, "fleiss_kappa": 0.9,
        }
        report, _ = self.generate([])
        self.assertIn("| relevant | a-b | 两两 κ | 0.600 | 合格 |", report)
        self.assertIn("| relevant | a-c | 两两 κ | 0.400 | 需修订定义 |", report)
        self.assertIn("| relevant | b-c | 两两 κ | 0.200 | 需重写定义 |", report)

    def test_threshold_boundaries(self):
        for value, expected in ((None, "没能判定"), (-0.1, "需重写定义"),
                                (0.3999, "需重写定义"), (0.4, "需修订定义"),
                                (0.5999, "需修订定义"), (0.6, "合格"), (1.0, "合格")):
            with self.subTest(value=value):
                self.assertEqual(verdict(value), expected)


if __name__ == "__main__":
    unittest.main()
