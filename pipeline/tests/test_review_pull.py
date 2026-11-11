from contextlib import redirect_stdout
from copy import deepcopy
import importlib
import io
from pathlib import Path
import sys
import tempfile
from types import ModuleType, SimpleNamespace
import unittest
from unittest.mock import patch

from pipeline.tests._support import read_jsonl, valid_labels, write_jsonl
from check_labels import check

with patch.dict(sys.modules, {"argilla": ModuleType("argilla")}):
    review_argilla = importlib.import_module("review_argilla")

apply_decision = review_argilla.apply_decision


class ApplyDecisionTests(unittest.TestCase):
    def test_off_topic_preserves_all_other_genes(self):
        labels = valid_labels()
        result, notes = apply_decision(
            labels, {"relevant": "off_topic", "g5_touchpoint": ["voice"],
                     "g16_severity": "p0"}, {"grok": valid_labels()})
        self.assertEqual(result, {**labels, "relevant": "off_topic"})
        self.assertEqual(notes, [])
        self.assertEqual(check(result), [])

    def test_yes_uses_other_full_annotation_then_decision(self):
        other = {"id": "fixture", **valid_labels(g16_severity="p2")}
        labels = {"relevant": "off_topic", "g13_expected": "旧值"}
        decision = {"relevant": "yes", "g16_severity": "p0"}
        raw = {"codex": labels, "grok": other}
        original = deepcopy((labels, decision, raw))
        result, notes = apply_decision(labels, decision, raw)
        self.assertEqual(result, valid_labels(g16_severity="p0"))
        self.assertEqual(notes, ["filled_from=grok"])
        self.assertEqual(check(result), [])
        self.assertEqual((labels, decision, raw), original)

    def test_other_annotator_is_selected_by_main(self):
        labels = {"relevant": "off_topic"}
        result, notes = apply_decision(
            labels, {"relevant": "yes"},
            {"grok": labels, "codex": valid_labels()}, main="grok")
        self.assertEqual(result, valid_labels())
        self.assertEqual(notes, ["filled_from=codex"])

    def test_yes_without_complete_other_is_marked_incomplete(self):
        for other in (None, {"relevant": "off_topic"},
                      {"relevant": "yes", "g5_touchpoint": ["memory"]}):
            with self.subTest(other=other):
                raw = {"codex": {"relevant": "off_topic"}}
                if other is not None:
                    raw["grok"] = other
                result, notes = apply_decision(
                    {"relevant": "off_topic"}, {"relevant": "yes"}, raw)
                self.assertEqual(result["relevant"], "yes")
                self.assertIn("incomplete", notes)
                self.assertTrue(check(result))

    def test_touchpoint_filters_unions_deduplicates_and_fills(self):
        labels = valid_labels(g5_touchpoint=["memory", "persona"],
                              g6_subtouch=["memory.cross_session", "persona.ooc",
                                           "memory.cross_session"])
        raw = {"codex": valid_labels(g6_subtouch=["memory.other"]),
               "grok": valid_labels(g6_subtouch=["memory.cross_session",
                                                 "memory.in_session", "persona.ooc"])}
        decision = {"g5_touchpoint": ["voice", "memory", "platform"]}
        original = deepcopy((labels, decision, raw))
        result, notes = apply_decision(labels, decision, raw)
        self.assertEqual(result["g6_subtouch"], [
            "memory.cross_session", "memory.in_session", "voice.other", "platform.other"])
        self.assertEqual(notes, ["g6_subtouch_removed=persona.ooc",
                                 "g6_subtouch_added=memory.in_session",
                                 "g6_subtouch_added=voice.other",
                                 "g6_subtouch_added=platform.other"])
        self.assertEqual(check(result), [])
        self.assertEqual((labels, decision, raw), original)

    def test_yes_and_touchpoint_decisions_are_applied_together(self):
        result, notes = apply_decision(
            {"relevant": "off_topic"},
            {"relevant": "yes", "g5_touchpoint": ["voice"], "g15_solvable": "platform"},
            {"grok": valid_labels()})
        self.assertEqual(result["g6_subtouch"], ["voice.other"])
        self.assertEqual(result["g15_solvable"], "platform")
        self.assertIn("filled_from=grok", notes)
        self.assertIn("g6_subtouch_removed=memory.cross_session", notes)
        self.assertEqual(check(result), [])

    def test_other_decision_keys_override_directly(self):
        labels = valid_labels()
        decision = {"g15_solvable": "business", "g16_severity": "p0"}
        result, notes = apply_decision(labels, decision, {"grok": valid_labels()})
        self.assertEqual(result, {**labels, **decision})
        self.assertEqual(notes, [])
        self.assertEqual(check(result), [])

    def test_unknown_touchpoint_leaves_optional_subtouch_empty(self):
        result, notes = apply_decision(valid_labels(), {"g5_touchpoint": ["unknown"]}, {})
        self.assertEqual(result["g5_touchpoint"], ["unknown"])
        self.assertEqual(result["g6_subtouch"], [])
        self.assertEqual(notes, ["g6_subtouch_removed=memory.cross_session"])
        self.assertEqual(check(result), [])


class PullTests(unittest.TestCase):
    def run_pull(self, labels, decision, raw):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            args = SimpleNamespace(final=root / "final.jsonl", merged=root / "merged.jsonl",
                                   decisions=root / "decisions.jsonl")
            untouched = {"id": "untouched", "labels": valid_labels()}
            write_jsonl(args.final, [{"id": "reviewed", "labels": labels}, untouched])
            write_jsonl(args.merged, [{"id": "reviewed", "raw": raw}])
            responses = [SimpleNamespace(status="submitted", question_name=k, value=v)
                         for k, v in decision.items()]
            responses.append(SimpleNamespace(status="draft", question_name="g16_severity",
                                             value="invalid-draft-value"))
            records = [SimpleNamespace(id="reviewed", responses=responses),
                       SimpleNamespace(id="untouched", responses=[])]
            output = io.StringIO()
            exit_code = 0
            with patch.object(review_argilla, "client") as client, redirect_stdout(output):
                client.return_value.datasets.return_value.records.return_value = records
                try:
                    review_argilla.pull(args)
                except SystemExit as exc:
                    exit_code = exc.code
                client.return_value.datasets.assert_called_once_with(review_argilla.NAME)
                client.return_value.datasets.return_value.records.assert_called_once_with(
                    with_responses=True)
            result = read_jsonl(args.final)
            self.assertEqual(result[1], untouched)
            self.assertEqual(read_jsonl(args.decisions), [{"id": "reviewed", "decision": decision}])
            return result[0], output.getvalue(), exit_code

    def test_pull_saves_dependent_before_and_counts(self):
        labels = valid_labels()
        result, output, code = self.run_pull(labels, {"g5_touchpoint": ["voice"]}, {})
        self.assertEqual(code, 0)
        self.assertEqual(check(result["labels"]), [])
        self.assertEqual(result["review"], {
            "decided": True,
            "before": {"g5_touchpoint": ["memory"], "g6_subtouch": ["memory.cross_session"]},
            "notes": ["g6_subtouch_removed=memory.cross_session", "g6_subtouch_added=voice.other"],
        })
        self.assertIn("已覆盖条数：1；改动主标注条数：1；校验不通过条数：0", output)

    def test_pull_records_filled_genes_in_before(self):
        result, _, code = self.run_pull({"relevant": "off_topic"}, {"relevant": "yes"},
                                        {"grok": valid_labels()})
        self.assertEqual(code, 0)
        self.assertEqual(result["review"]["before"],
                         {k: "off_topic" if k == "relevant" else None for k in valid_labels()})
        self.assertEqual(result["review"]["notes"], ["filled_from=grok"])

    def test_pull_writes_invalid_details_and_exits_one(self):
        result, output, code = self.run_pull({"relevant": "off_topic"}, {"relevant": "yes"}, {})
        self.assertEqual(code, 1)
        self.assertTrue(result["review"]["decided"])
        self.assertEqual(result["review"]["notes"], ["incomplete"])
        self.assertEqual(result["review"]["invalid"], check(result["labels"]))
        self.assertTrue(result["review"]["invalid"])
        self.assertIn("已覆盖条数：1；改动主标注条数：1；校验不通过条数：1", output)

    def test_pull_unchanged_decision_is_covered_but_not_changed(self):
        result, output, code = self.run_pull(valid_labels(), {"g16_severity": "p1"}, {})
        self.assertEqual(code, 0)
        self.assertEqual(result["labels"], valid_labels())
        self.assertNotIn("invalid", result["review"])
        self.assertIn("已覆盖条数：1；改动主标注条数：0；校验不通过条数：0", output)


if __name__ == "__main__":
    unittest.main()
