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


class AgreementPatchTests(unittest.TestCase):
    def test_patches_precede_validation_skip_off_topic_and_count_matches(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            off = {"relevant": "off_topic", "g17_risk": []}
            write_jsonl(root / "a.jsonl", [
                {"id": "repair", "labels": valid_labels(g17_risk=["invalid"])},
                {"id": "same", "labels": valid_labels()},
                {"id": "off", "labels": off},
            ])
            write_jsonl(root / "b.jsonl", [
                {"id": "repair", **valid_labels(g17_risk=["dependency"])},
                {"id": "same", **valid_labels()}, {"id": "off", **off},
            ])
            write_jsonl(root / "patches" / "01.jsonl", [
                {"id": "repair", "g17_risk": ["minor"]},
                {"id": "same", "g17_risk": []},
                {"id": "off", "g17_risk": ["minor"]},
                {"id": "unmatched", "g17_risk": ["minor"]},
            ])
            write_jsonl(root / "patches" / "02.jsonl", [
                {"id": "repair", "g17_risk": ["dependency"]},
            ])
            write_jsonl(root / "second.jsonl", [
                {"id": "repair", "g17_risk": ["data_loss"]},
            ])
            write_jsonl(root / "b-patch.jsonl", [
                {"id": "repair", "g17_risk": ["data_loss"]},
            ])
            out = root / "report"
            base = ("--ann", f"a={root / 'a.jsonl'}", "--ann", f"b={root / 'b.jsonl'}")
            result = run_cli("label/agreement.py", *base, "--out", out, cwd=root)
            assert_success(self, result)
            original = json.loads((out / "agreement.json").read_text(encoding="utf-8"))
            self.assertEqual(original["usable"], 2)
            self.assertEqual(original["undetermined"], {"a": 1, "b": 0})
            self.assertNotIn("patches", original)
            result = run_cli(
                "label/agreement.py", *base,
                "--patch", f"a:g17_risk={root / 'patches'}",
                "--patch", f"a:g17_risk={root / 'second.jsonl'}",
                "--patch", f"b:g17_risk={root / 'b-patch.jsonl'}", "--out", out, cwd=root,
            )
            assert_success(self, result)
            report = json.loads((out / "agreement.json").read_text(encoding="utf-8"))
            self.assertEqual(report["patches"], [
                {"annotator": "a", "gene": "g17_risk", "path": str(root / "patches"), "applied": 2},
                {"annotator": "a", "gene": "g17_risk", "path": str(root / "second.jsonl"), "applied": 1},
                {"annotator": "b", "gene": "g17_risk", "path": str(root / "b-patch.jsonl"), "applied": 1},
            ])
            self.assertEqual(report["sample"], 3)
            self.assertEqual(report["usable"], 3)
            self.assertEqual(report["both_relevant"], 2)
            self.assertEqual(report["undetermined"], {"a": 0, "b": 0})
            self.assertEqual(report["genes"]["g17_risk"]["pairwise"]["a-b"]["mean_label_kappa"], 1.0)
            merged = {r["id"]: r for r in read_jsonl(out / "merged.jsonl")}
            self.assertEqual(merged["repair"]["labels"], valid_labels(g17_risk=["data_loss"]))
            self.assertEqual(merged["off"]["labels"], off)
            self.assertNotIn("unmatched", merged)

    def test_invalid_patch_value_still_fails_annotation_validation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_jsonl(root / "a.jsonl", [{"id": "one", **valid_labels()}])
            write_jsonl(root / "patch.jsonl", [{"id": "one", "g17_risk": ["invalid"]}])
            out = root / "report"
            result = run_cli(
                "label/agreement.py", "--ann", f"a={root / 'a.jsonl'}",
                "--ann", f"b={root / 'a.jsonl'}", "--patch", f"a:g17_risk={root / 'patch.jsonl'}",
                "--out", out, cwd=root,
            )
            assert_success(self, result)
            report = json.loads((out / "agreement.json").read_text(encoding="utf-8"))
            self.assertEqual(report["usable"], 0)
            self.assertEqual(report["undetermined"], {"a": 1, "b": 0})
            self.assertEqual(report["patches"][0]["applied"], 1)

    def test_invalid_patch_target_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            write_jsonl(root / "a.jsonl", [{"id": "one", **valid_labels()}])
            for spec in ("bad-format", "missing:g17_risk=unused", "a:missing=unused", "a:g17_risk="):
                with self.subTest(spec=spec):
                    result = run_cli("label/agreement.py", "--ann", f"a={root / 'a.jsonl'}",
                                     "--patch", spec, "--out", root / "report", cwd=root)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("--patch", result.stderr)
                    self.assertFalse((root / "report").exists())
