import json
from pathlib import Path
import tempfile
import unittest

from tests._support import assert_success, read_jsonl, run_cli, valid_labels, write_jsonl
from s06_product_definition import code as genome_report
from s04_labeling import code as merge_final


class MergeReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.src = self.root / "clean.jsonl"
        self.merged = self.root / "output" / "final.jsonl"
        self.report = self.root / "reports" / "genome.md"
        # Each comment has a distinctive canary. G13 intentionally quotes one
        # so the privacy assertion also catches free-text label leakage.
        self.comments = {
            "full": "原文哨兵甲Q7V4：这是仅供测试使用的独特评论。",
            "double": "原文哨兵乙R8W5：另一条仅供测试使用的独特评论。",
            "off": "原文哨兵丙S9X6：这条内容与产品无关。",
        }
        self.clean = [
            {"id": rid, "app": "fixture-app", "rating": 3, "date": "2000-01-01",
             "text": text, "low_info": False}
            for rid, text in self.comments.items()
        ]
        self.full_labels = valid_labels(g17_risk=["dependency"])
        self.double_labels = valid_labels(
            g16_severity="p2", g17_risk=["dependency"],
            g13_expected="Agent 应当回应：" + self.comments["double"],
        )
        self.off_labels = {"relevant": "off_topic", "g17_risk": []}
        write_jsonl(self.src, self.clean)
        write_jsonl(self.root / "full" / "a" / "chunk.jsonl", [
            {"id": "full", **self.full_labels}, {"id": "off", **self.off_labels},
        ])
        write_jsonl(self.root / "double" / "a" / "chunk.jsonl", [
            {"id": "double", **self.double_labels},
        ])
        write_jsonl(self.root / "full" / "a-g17_risk" / "chunk.jsonl", [
            {"id": "full", "g17_risk": ["billing_dispute"]},
            {"id": "off", "g17_risk": ["minor"]},
        ])
        write_jsonl(self.root / "double" / "a-g17_risk" / "chunk.jsonl", [
            {"id": "double", "g17_risk": ["data_loss"]},
        ])
        self.review = self.root / "double" / "report" / "merged.jsonl"
        write_jsonl(self.review, [{"id": "double", "needs_review": ["g16_severity"]}])

    def merge(self):
        result = run_cli(
            "s04_labeling/code.py", "merge", "--main", "a", "--dirs",
            f"{self.root / 'full'},{self.root / 'double'}", "--relabeled", "g17_risk",
            "--review", self.review, "--src", self.src, "--out", self.merged, cwd=self.root,
        )
        assert_success(self, result)
        stats = json.loads(result.stdout)
        self.assertEqual(stats["total_written"], 3)
        self.assertEqual(stats.get("invalid", 0), 0)
        self.assertEqual(stats.get("missing", 0), 0)
        self.assertEqual(stats.get("missing_relabel_g17_risk", 0), 0)
        records = read_jsonl(self.merged)
        self.assertEqual(len(records), 3)
        return {r["id"]: r for r in records}

    def generate_report(self, src):
        result = run_cli("s06_product_definition/code.py", "genome-report", "--src", src,
                         "--out", self.report, cwd=self.root)
        assert_success(self, result)
        self.assertTrue(self.report.is_file())
        return self.report.read_text(encoding="utf-8")

    def test_cli_merge_replaces_g17_from_both_directories(self):
        rows = self.merge()
        self.assertEqual(rows["full"]["labels"], {**self.full_labels, "g17_risk": ["billing_dispute"]})
        self.assertEqual(rows["double"]["labels"], {**self.double_labels, "g17_risk": ["data_loss"]})
        self.assertEqual(merge_final.GENOME, genome_report.GENOME)

    def test_cli_merge_does_not_relabel_off_topic(self):
        rows = self.merge()
        self.assertEqual(rows["off"]["labels"], self.off_labels)

    def test_cli_merge_preserves_review_flags(self):
        rows = self.merge()
        self.assertEqual(rows["double"]["needs_review"], ["g16_severity"])
        self.assertTrue(rows["double"]["in_double_sample"])
        for rid in ("full", "off"):
            self.assertEqual(rows[rid]["needs_review"], [])
            self.assertFalse(rows[rid]["in_double_sample"])

    def test_cli_report_cross_table_and_no_comment_text(self):
        rows = self.merge()
        for rid, comment in self.comments.items():
            self.assertEqual(rows[rid]["text"], comment)
        report = self.generate_report(self.merged)
        self.assertIn("3 条已标注，其中与陪伴产品相关 2 条，不相关 1 条", report)
        self.assertIn("一级触点 × 严重度", report)
        self.assertIn("| 触点 | P0 | P1 | P2 | 无问题 | 合计 |", report)
        self.assertIn("| 记忆（`memory`） | 0 | 1 | 1 | 0 | 2 |", report)
        for comment in self.comments.values():
            with self.subTest(comment_canary=comment.split("：")[0]):
                self.assertNotIn(comment, report)
                self.assertNotIn(comment.split("：")[0], report)

    def test_cli_report_empty_input(self):
        src = self.root / "empty.jsonl"
        write_jsonl(src, [])
        report = self.generate_report(src)
        self.assertIn("0 条已标注，其中与陪伴产品相关 0 条", report)
        self.assertIn("一级触点 × 严重度", report)
        self.assertIn("0 条（0.0%）", report)

    def test_cli_report_all_off_topic(self):
        rows = self.merge()
        src = self.root / "off-topic.jsonl"
        write_jsonl(src, [rows["off"]])
        report = self.generate_report(src)
        self.assertIn("1 条已标注，其中与陪伴产品相关 0 条，不相关 1 条", report)
        self.assertIn("一级触点 × 严重度", report)
        self.assertIn("0 条（0.0%）", report)
        self.assertNotIn(self.comments["off"], report)


if __name__ == "__main__":
    unittest.main()
