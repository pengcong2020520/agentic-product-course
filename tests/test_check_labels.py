from pathlib import Path
import tempfile
import unittest

from tests._support import run_cli, valid_labels, write_jsonl
from s03_product_genome.code import GENOME, check


class CheckLabelsTests(unittest.TestCase):
    def test_all_valid_labels(self):
        labels = valid_labels()
        self.assertEqual(set(labels), {gene["id"] for gene in GENOME["genes"]})
        self.assertEqual(check(labels), [])

    def test_invalid_single_value(self):
        self.assertEqual(check(valid_labels(g8_emotion="invalid")), ["g8_emotion='invalid'"])

    def test_required_multi_cannot_be_empty(self):
        self.assertEqual(check(valid_labels(g1_user=[])), ["g1_user=[]"])

    def test_multi_exceeds_max(self):
        values = ["memory", "persona", "dialogue", "agency"]
        self.assertEqual(check(valid_labels(g5_touchpoint=values)), [f"g5_touchpoint={values!r}"])

    def test_subtouch_must_belong_to_selected_parent(self):
        self.assertEqual(check(valid_labels(g6_subtouch=["persona.ooc"])),
                         ["g6_subtouch=['persona.ooc']"])

    def test_off_topic_allows_missing_genes(self):
        self.assertEqual(check({"relevant": "off_topic"}), [])

    def test_only_risk_ignores_other_genes(self):
        self.assertEqual(check({"g17_risk": ["minor"], "g8_emotion": "invalid"}, only={"g17_risk"}), [])
        self.assertEqual(check({"g17_risk": ["invalid"]}, only={"g17_risk"}),
                         ["g17_risk=['invalid']"])

    def test_cli_mismatched_ids_exit_one(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src, out = root / "input.jsonl", root / "labels.jsonl"
            write_jsonl(src, [{"id": "input-id"}])
            write_jsonl(out, [{"id": "different-id", **valid_labels()}])
            result = run_cli("s03_product_genome/code.py", "check", src, out, cwd=root)
            self.assertEqual(result.returncode, 1, result.stdout + result.stderr)
            self.assertEqual(result.stdout.strip(), "id 不对应：输入 1 条，输出 1 条")
            self.assertEqual(result.stderr, "")


if __name__ == "__main__":
    unittest.main()
