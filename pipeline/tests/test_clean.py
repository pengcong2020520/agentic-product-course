from collections import Counter
import json
from pathlib import Path
import tempfile
import unittest

from pipeline.tests._support import assert_success, read_jsonl, run_cli, write_jsonl
from clean import normalize, scrub


class CleanTests(unittest.TestCase):
    def test_normalize_fullwidth(self):
        self.assertEqual(normalize("ＡＢＣ１２３，！　中文"), "ABC123,! 中文")

    def test_normalize_collapses_whitespace(self):
        self.assertEqual(normalize(" \t甲\n\r乙   丙\u3000 "), "甲 乙 丙")

    def test_scrub_placeholders_and_counts(self):
        # Synthetic pattern fixtures, not real contact or identity information.
        cases = {
            "[手机号]": "19900000000",
            "[邮箱]": "fixture@example.com",
            "[链接]": "https://example.invalid/fixture",
            "[身份证]": "00000000000000000X",
            "[账号]": "微信号 abc12345",
        }
        for tag, value in cases.items():
            with self.subTest(tag=tag):
                counts = Counter()
                self.assertEqual(scrub(f"{value} {value}", counts), f"{tag} {tag}")
                self.assertEqual(counts[tag], 2)
                self.assertEqual(sum(counts.values()), 2)
        counts = Counter()
        self.assertEqual(scrub(" ".join(cases.values()), counts), " ".join(cases))
        self.assertEqual(dict(counts), {tag: 1 for tag in cases})

    def test_scrub_preserves_ordinary_numbers(self):
        counts = Counter()
        text = "使用 40 周，累计 2,000 次。"
        self.assertEqual(scrub(text, counts), text)
        self.assertEqual(sum(counts.values()), 0)

    def test_cli_deduplication_and_low_info_counts(self):
        long_text = "每天打开应用都会继续昨天的故事角色能够记住之前的约定并且自然地推动后续情节让我愿意长期使用这个功能"
        contents = [long_text, long_text, long_text + "呀", "好用", "语音播放时总是突然中断需要重新加载", "希望增加导出记录功能方便保存重要内容"]
        rows = [{"id": f"clean-{i}", "app": "fixture-app", "title": "", "content": text}
                for i, text in enumerate(contents)]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            src, out = root / "raw.jsonl", root / "output" / "clean.jsonl"
            write_jsonl(src, rows)
            result = run_cli("clean/clean.py", "--src", src, "--out", out, cwd=root)
            assert_success(self, result)
            report = json.loads(out.with_suffix(".report.json").read_text(encoding="utf-8"))
            self.assertEqual(report["input"], 6)
            self.assertEqual(report["after_exact_dedup"], 5)
            self.assertEqual(report["after_near_dedup"], 4)
            self.assertEqual(report["low_info"], 1)
            self.assertEqual(report["to_label"], 3)
            self.assertEqual(json.loads(result.stdout), report)
            cleaned = read_jsonl(out)
            self.assertEqual([r["id"] for r in cleaned], ["clean-0", "clean-3", "clean-4", "clean-5"])
            self.assertEqual([r["id"] for r in cleaned if r["low_info"]], ["clean-3"])
            self.assertTrue(all("title" not in r and "content" not in r for r in cleaned))


if __name__ == "__main__":
    unittest.main()
