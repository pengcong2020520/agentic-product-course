from pathlib import Path
import tempfile
import unittest

from s06_product_definition import code as report
from tests._support import assert_success, run_cli, valid_labels, write_jsonl


def row(**overrides):
    return {"labels": valid_labels(g1_user=["unknown"], g2_motive=["unknown"], **overrides)}


class SegmentReportTests(unittest.TestCase):
    def summarize(self, **labels):
        return report.summarize([{"labels": valid_labels(**labels)}])[1]

    def test_every_profile_and_unknown(self):
        for profile in report.GENES["g1_user"]["values"]:
            with self.subTest(profile=profile):
                segments = self.summarize(g1_user=[profile], g2_motive=[])
                self.assertNotIn("unknown", segments)
                for key in report.SEGMENTS.keys() - {"陪伴向", "创作向"}:
                    self.assertEqual(segments[key]["count"], int(key == profile))

    def test_merged_slice_each_inclusion_rule(self):
        for profile in ("dream_partner", "confider", "creator"):
            with self.subTest(profile=profile):
                segments = self.summarize(g1_user=[profile], g2_motive=[])
                self.assertEqual(segments["陪伴向"]["count"], int(profile != "creator"))
                self.assertEqual(segments["创作向"]["count"], int(profile == "creator"))
        for motive in ("companionship", "emotional_support", "romance", "creation", "roleplay"):
            with self.subTest(motive=motive):
                segments = self.summarize(g1_user=["unknown"], g2_motive=[motive])
                self.assertEqual(segments["陪伴向"]["count"], int(motive in {
                    "companionship", "emotional_support", "romance"}))
                self.assertEqual(segments["创作向"]["count"], int(motive == "creation"))

    def test_overlap_and_duplicates_count_once(self):
        segments = self.summarize(
            g1_user=["dream_partner", "confider", "creator", "creator"],
            g2_motive=["companionship", "romance", "creation"],
            g5_touchpoint=["memory", "memory", "dialogue"],
            g13_expected="Agent 应当记忆；Agent 应当回应。",
        )
        for key in ("dream_partner", "confider", "creator", "陪伴向", "创作向"):
            self.assertEqual(segments[key]["count"], 1)
            self.assertEqual(segments[key]["agent"], 1)
            self.assertEqual(segments[key]["genes"]["g5_touchpoint"], {"memory": 1, "dialogue": 1})

    def test_denominators_and_all_six_distributions(self):
        rows = [
            {"labels": valid_labels(g16_severity="p0")},
            {"labels": valid_labels(g16_severity="p1", g13_expected="产品应当改善。")},
            {"labels": valid_labels(g16_severity="p2", g13_expected=None,
                                    g5_touchpoint=[], g6_subtouch=[])},
            row(g13_expected="", g16_severity="none"),
            {"labels": valid_labels(relevant="off_topic")},
            {"labels": valid_labels(relevant=None)},
        ]
        relevant, segments = report.summarize(rows)
        self.assertEqual(relevant, 4)
        segment = segments["confider"]
        self.assertEqual((segment["count"], segment["agent"], segment["p0_p1"]), (3, 1, 2))
        text = report.render_report(relevant, segments)
        detail = text.split("## 倾诉者（`confider`）\n", 1)[1].split("\n## ", 1)[0]
        for expected in (
            "样本数：3 条；占相关样本：75.0%", "写了“Agent 应当”：1 条（33.3%）",
            "P0+P1：2 条（66.7%）", "| 记忆（`memory`） | 2 | 66.7% |",
            "| 跨会话失忆、隔天不记得（`memory.cross_session`） | 2 | 66.7% |",
            "| 不孤单（`not_alone`） | 3 | 100.0% |",
            "| 记忆基建（`cap.memory`） | 3 | 100.0% |",
            "| P0 流失/扣费/丢数据（`p0`） | 1 | 33.3% |",
            "| 持续使用（`ongoing`） | 3 | 100.0% |",
        ):
            self.assertIn(expected, detail)
        self.assertIn("| 倾诉者（`confider`） | 3 | 66.7% | 33.3% |", text)

    def test_top_eight_and_top_three_with_stable_ties(self):
        keys = list(report.GENES["g5_touchpoint"]["values"])[:10]
        rows = [{"labels": valid_labels(g5_touchpoint=[key])} for key in keys]
        rows.append({"labels": valid_labels(g5_touchpoint=["memory"])})
        relevant, segments = report.summarize(rows)
        text = report.render_report(relevant, segments)
        self.assertEqual(text, report.render_report(*report.summarize(reversed(rows))))
        detail = text.split("## 倾诉者（`confider`）\n", 1)[1].split("\n## ", 1)[0]
        table = detail.split("### ", 1)[1].split("### ", 1)[0]
        data_rows = [line for line in table.splitlines() if line.startswith("| ")][1:]
        self.assertEqual(len(data_rows), 8)
        self.assertEqual(data_rows[0], "| 记忆（`memory`） | 2 | 18.2% |")
        comparison = text.split("## 切片对比\n", 1)[1]
        line = next(line for line in comparison.splitlines() if line.startswith("| 倾诉者"))
        touchpoints = line.split("|")[5]
        self.assertEqual(touchpoints.count("："), 3)
        self.assertIn("记忆（`memory`）：2（18.2%）", touchpoints)
        self.assertIn("主动与推进（`agency`）", touchpoints)
        self.assertIn("创作工具（`creation_tool`）", touchpoints)

    def test_empty_all_off_topic_and_missing_optional_labels(self):
        for rows in ([], [{"labels": {"relevant": "off_topic"}}],
                     [{"labels": {"relevant": "yes", "g1_user": ["creator"]}}]):
            with self.subTest(rows=rows):
                relevant, segments = report.summarize(rows)
                text = report.render_report(relevant, segments)
                self.assertEqual(len(segments), 9)
                self.assertIn("| 陪伴向 | 0 | 0.0% | 0.0% | — | — |", text)
                self.assertNotIn("nan", text)

    def test_cli_defaults_custom_paths_and_privacy(self):
        canaries = ["评论哨兵Q7V4", "自由文本哨兵R8W5", "标识哨兵S9X6", "元数据哨兵T1Y2"]
        sample = {"id": canaries[2], "app": canaries[3], "text": canaries[0],
                  "labels": valid_labels(g13_expected="Agent 应当" + canaries[1])}
        # 未知枚举即便意外混入原文，也不能被当成标签名称输出。
        sample["labels"]["g5_touchpoint"].append(canaries[0])
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for defaults in (False, True):
                with self.subTest(defaults=defaults):
                    src = root / ("data/labeled/genome-final.jsonl" if defaults else "input.jsonl")
                    out = root / ("data/reports/segment-report.md" if defaults else "nested/report.md")
                    write_jsonl(src, [sample])
                    args = () if defaults else ("--src", src, "--out", out)
                    result = run_cli("s06_product_definition/code.py", "segment-report", *args, cwd=root)
                    assert_success(self, result)
                    text = out.read_text(encoding="utf-8")
                    self.assertIn("相关样本：1 条", text)
                    self.assertIn("写了“Agent 应当”：1 条（100.0%）", text)
                    for canary in canaries:
                        self.assertNotIn(canary, text + result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
