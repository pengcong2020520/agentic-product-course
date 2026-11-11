import json
from pathlib import Path
import tempfile
import unittest

from pipeline.tests._support import assert_success, read_jsonl, run_cli, valid_labels, write_jsonl
from agreement import cohen, fleiss, jaccard, weighted


class AgreementTests(unittest.TestCase):
    def test_perfect_agreement(self):
        self.assertEqual(cohen(["a", "b", "a"], ["a", "b", "a"]), 1.0)
        self.assertEqual(fleiss([["a"] * 3, ["b"] * 3], ["a", "b"]), 1.0)
        self.assertEqual(weighted([1, 2, 3], [1, 2, 3]), 1.0)
        self.assertEqual(jaccard(["a", "b"], ["b", "a"]), 1.0)

    def test_cohen_textbook_contingency_table(self):
        # 2x2 table [[20, 5], [10, 15]], N=50:
        # Po=35/50=.7; Pe=(25*30+25*20)/2500=.5; kappa=.4.
        a = ["yes"] * 25 + ["no"] * 25
        b = ["yes"] * 20 + ["no"] * 5 + ["yes"] * 10 + ["no"] * 15
        self.assertEqual(round(cohen(a, b), 3), 0.400)

    def test_fleiss_small_example(self):
        # Three raters, four subjects; Pi=(1, 1, 1/3, 1/3).
        # Pbar=2/3; category proportions=(1/2,1/2); Pe=1/2; kappa=1/3.
        rows = [["a", "a", "a"], ["b", "b", "b"],
                ["a", "a", "b"], ["a", "b", "b"]]
        self.assertEqual(round(fleiss(rows, ["a", "b"]), 3), 0.333)

    def test_weighted_adjacent_rating_gets_half_credit(self):
        # Weights for pairs (1,1),(2,3),(3,3) are 1,.5,1: Po=5/6.
        # Nine cross-pair weights sum to 4.5: Pe=1/2; kappa=2/3.
        # Half credit is the pair's weight, not the chance-corrected kappa.
        self.assertEqual(round(weighted([1, 2, 3], [1, 3, 3]), 3), 0.667)

    def test_jaccard_empty_sets(self):
        self.assertEqual(jaccard([], []), 1.0)
        self.assertEqual(jaccard(["a"], []), 0.0)

    def test_jaccard_partial_overlap(self):
        self.assertEqual(round(jaccard(["a", "b"], ["b", "c"]), 3), 0.333)

    def test_cli_flags_severity_and_preserves_first_annotator(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            first = [{"id": f"agreement-{i}", "labels": valid_labels(g16_severity=sev)}
                     for i, sev in enumerate(["p0", "p1", "p2"])]
            second = [{"id": f"agreement-{i}", **valid_labels(g16_severity=sev)}
                      for i, sev in enumerate(["p0", "p2", "p2"])]
            write_jsonl(root / "a" / "chunk.jsonl", first)
            write_jsonl(root / "b" / "chunk.jsonl", second)
            out = root / "report"
            result = run_cli("label/agreement.py", "--ann", f"a={root / 'a'}",
                             "--ann", f"b={root / 'b'}", "--out", out, cwd=root)
            assert_success(self, result)
            merged = read_jsonl(out / "merged.jsonl")
            self.assertEqual([r["id"] for r in merged], [r["id"] for r in first])
            self.assertEqual([r["labels"] for r in merged], [r["labels"] for r in first])
            self.assertEqual([r["needs_review"] for r in merged], [[], ["g16_severity"], []])
            report = json.loads((out / "agreement.json").read_text(encoding="utf-8"))
            self.assertEqual(report["sample"], 3)
            self.assertEqual(report["usable"], 3)
            self.assertEqual(report["needs_review"], 1)
            self.assertEqual(report["undetermined"], {"a": 0, "b": 0})


if __name__ == "__main__":
    unittest.main()
