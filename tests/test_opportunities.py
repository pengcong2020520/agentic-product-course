"""Synthetic opportunity-map fixtures; never read the labeled data directory."""

import json
import math

import pytest

from s06_product_definition import code as report
from tests._support import run_cli, write_jsonl


def sample(sample_id, **labels):
    return {
        "id": sample_id, "text": "评论原文哨兵", "app": "应用哨兵", "rating": 1,
        "labels": {"relevant": "yes", "g6_subtouch": ["memory.cross_session"],
                   "g13_expected": "期望原文哨兵", **labels},
    }


def sentence(sample_id, themes, index=0):
    return {"id": sample_id, "sentence_index": index,
            "sentence": "行为句子原文哨兵", "themes": themes}


def fixtures():
    rows = [
        sample("标识哨兵0", g16_severity="p0", g8_intensity=1, g10_stage="churning",
               g15_solvable="mixed", g4_investment="paying",
               g1_user=["dream_partner", "confider", "story_player", "creator", "power_user"],
               g6_subtouch=["memory.cross_session", "memory.cross_session", "memory.other",
                            "评论原文哨兵"]),
        sample("标识哨兵1", g16_severity="p1", g8_intensity=3, g10_stage="veteran",
               g15_solvable="agent", g4_investment="paying",
               g2_motive=["companionship", "creation", "creation"],
               g6_subtouch=["memory.cross_session", "persona.ooc"]),
        sample("标识哨兵2", g16_severity="p2", g8_intensity=None, g10_stage="ongoing",
               g15_solvable="platform", g1_user=["tool_user"]),
        sample("标识哨兵3", g16_severity="none", g8_intensity=2, g15_solvable="business",
               g1_user=["story_player"], g2_motive=["emotional_support", "romance"]),
        sample("不相关哨兵", relevant="off_topic", g16_severity="p0", g8_intensity=3,
               g6_subtouch=["memory.cross_session", "dialogue.repetition"]),
    ]
    themes = [sentence(row["id"], ["remember_facts"]) for row in rows]
    themes += [sentence("标识哨兵0", ["remember_facts", "remember_facts"], 1),
               sentence("标识哨兵1", ["hold_persona"]),
               sentence("不存在哨兵", ["orphan_theme"]),
               sentence("不相关哨兵", ["off_topic_theme"])]
    return rows, themes


def test_metric_denominators_overlap_other_and_theme_deduplication():
    rows, themes = fixtures()
    result = report.build_opportunity_map(rows, themes, min_n=2)
    assert result["relevant_n"] == 4
    for key in ("pain", "behavior"):
        table = result[key]
        assert (table["candidate_count"], table["filtered_count"], table["retained_count"]) == (2, 1, 1)
        row = table["rows"][0]
        assert row["n"] == 4
        for metric, expected in {
            "pain": 0.5, "intensity": 2, "intensity_n": 3,
            "churn": 0.25, "regress": 0.25, "agent_share": 0.5,
            "platform_share": 0.5, "business_share": 0.25, "paying": 0.5,
            "size": 1, "severity": 0.425, "solvable": 0.5, "score": 0.2125,
        }.items():
            assert row[metric] == pytest.approx(expected)
        assert row["segments"] == {"陪伴向": 3, "剧情玩家": 2, "创作向": 2,
                                   "进阶玩家": 1, "其他/不明": 1}
        assert row["ranks"] == {"default": 1, "size_light": 1, "pain_heavy": 1}
        assert row["stable"] is True
        assert table["stable_opportunities"] == [row["candidate"]]
    assert result["pain"]["excluded_other_count"] == 1
    assert result["pain"]["rows"][0]["candidate"] == "memory.cross_session"
    assert result["behavior"]["rows"][0]["candidate"] == "remember_facts"
    # The .other exclusion only applies to subtouch labels.
    other = report.build_opportunity_map(rows, [sentence("标识哨兵0", ["behavior.other"])], 1)
    assert other["behavior"]["rows"][0]["candidate"] == "behavior.other"


@pytest.mark.parametrize("gene,value,segment", [
    ("g1_user", "dream_partner", "陪伴向"), ("g1_user", "confider", "陪伴向"),
    ("g2_motive", "companionship", "陪伴向"), ("g2_motive", "emotional_support", "陪伴向"),
    ("g2_motive", "romance", "陪伴向"), ("g1_user", "story_player", "剧情玩家"),
    ("g1_user", "creator", "创作向"), ("g2_motive", "creation", "创作向"),
    ("g1_user", "power_user", "进阶玩家"), ("g1_user", "unknown", "其他/不明"),
    ("g2_motive", "roleplay", "其他/不明"),
])
def test_each_population_inclusion_rule(gene, value, segment):
    assert report.opportunity_segments({gene: [value, value]}) == {segment}


def test_sensitivity_ranks_top_ten_boundary_and_determinism():
    keys = [key for key in report.GENES["g6_subtouch"]["values"]
            if not key.endswith(".other")][:12]
    base_keys = sorted(keys[:10])
    small_key, low_key = keys[10:]
    rows, themes = [], []
    for key in keys:
        count = 2 if key == small_key else 4
        for i in range(count):
            sample_id = f"{key}-{i}"
            rows.append(sample(
                sample_id, g6_subtouch=[key], g15_solvable="agent",
                g16_severity="p1" if key != low_key or i < 2 else "p2",
                g8_intensity=3 if key == small_key else (2 if i < 2 else 3) if key == low_key else 1,
            ))
            themes.append(sentence(sample_id, [key]))
    result = report.build_opportunity_map(rows, themes, 1)
    for table in (result["pain"], result["behavior"]):
        by_key = {row["candidate"]: row for row in table["rows"]}
        assert [row["candidate"] for row in table["rows"]] == base_keys + [small_key, low_key]
        assert by_key[small_key]["ranks"] == {"default": 11, "size_light": 1, "pain_heavy": 1}
        assert by_key[small_key]["size"] == pytest.approx(math.log(3) / math.log(5))
        for index, key in enumerate(base_keys, 1):
            assert by_key[key]["ranks"] == {"default": index, "size_light": index + 1,
                                            "pain_heavy": index + 1}
        assert table["stable_opportunities"] == base_keys[:9]
    assert result == report.build_opportunity_map(reversed(rows), reversed(themes), 1)
    assert report.render_opportunity_map(result) == report.render_opportunity_map(
        report.build_opportunity_map(reversed(rows), reversed(themes), 1))


def test_missing_intensity_zero_scores_and_empty_tables():
    rows = [sample("one", g16_severity="p1", g15_solvable="mixed"),
            sample("two", g8_intensity=None, g15_solvable="business")]
    result = report.build_opportunity_map(rows, [], 1)
    row = result["pain"]["rows"][0]
    assert row["intensity"] is None
    assert row["intensity_n"] == 0
    assert row["severity"] == 0.25
    assert row["score"] == 0.125
    zero = report.build_opportunity_map([sample("one")], [], 1)["pain"]["rows"][0]
    assert zero["scores"] == {"default": 0, "size_light": 0, "pain_heavy": 0}
    for input_rows, min_n, filtered in (([], 1, 0), (rows, 3, 1),
                                       ([sample("one", relevant="off_topic")], 1, 0)):
        empty = report.build_opportunity_map(input_rows, [sentence("one", ["theme"])], min_n)
        assert empty["pain"]["rows"] == []
        assert empty["pain"]["max_n"] == 0
        assert empty["pain"]["filtered_count"] == filtered
        assert empty["behavior"]["rows"] == []
        assert "无。" in report.render_opportunity_map(empty)
        json.dumps(empty, allow_nan=False)


@pytest.mark.parametrize("use_defaults", [True, False])
def test_cli_paths_defaults_weights_and_report_privacy(tmp_path, use_defaults):
    rows, themes = fixtures()
    src = tmp_path / "data/labeled/genome-final.jsonl"
    theme_src = tmp_path / "data/labeled/agent-themes.jsonl"
    write_jsonl(src, rows)
    write_jsonl(theme_src, themes)
    out = tmp_path / "data/reports/opportunity-map.md"
    json_out = out.with_suffix(".json")
    args = []
    if not use_defaults:
        out = tmp_path / "custom/map.md"
        json_out = tmp_path / "separate/map.json"
        args = ["--src", src, "--themes", theme_src, "--out", out, "--json", json_out,
                "--min-n", "2", "--w1", "0.5", "--w2", "2", "--w3", "0"]
    completed = run_cli("s06_product_definition/code.py", "opportunities", *args, cwd=tmp_path)
    assert completed.returncode == 0, completed.stderr
    result = json.loads(json_out.read_text())
    markdown = out.read_text()
    assert result["min_n"] == (15 if use_defaults else 2)
    assert result["weights"]["default"] == ([1, 1, 1] if use_defaults else [0.5, 2, 0])
    if use_defaults:
        assert result["pain"]["filtered_count"] == 2
    else:
        assert result["pain"]["rows"][0]["score"] == pytest.approx(0.425 ** 2)
        assert "min-n 过滤 1 个" in markdown
        assert "| memory.cross_session | 4 | 50.00% | 2.0000 | 3 |" in markdown
        assert "3 / 2 / 2 / 1 / 1" in markdown
        assert "- remember_facts" in markdown.split("## 稳定机会")[1]
    for label in ("## A. 痛点机会", "## B. 行为机会", "## 稳定机会",
                  "名次 default", "名次 size_light", "名次 pain_heavy"):
        assert label in markdown
    combined = markdown + json_out.read_text() + completed.stdout + completed.stderr
    for canary in ("评论原文哨兵", "行为句子原文哨兵", "期望原文哨兵", "标识哨兵", "应用哨兵"):
        assert canary not in combined
    for forbidden in ("text", "sentence", "id", "app", "g13_expected"):
        assert f'"{forbidden}":' not in json_out.read_text()


@pytest.mark.parametrize("args", [["--min-n", "0"], ["--min-n", "-1"],
                                 ["--w1", "-1"], ["--w2", "nan"], ["--w3", "inf"]])
def test_invalid_parameters_fail_before_reading_inputs(tmp_path, args):
    completed = run_cli("s06_product_definition/code.py", "opportunities", *args, cwd=tmp_path)
    assert completed.returncode == 2
    assert "min-n 必须至少为 1；权重必须为非负有限数" in completed.stderr
    assert not (tmp_path / "data").exists()
