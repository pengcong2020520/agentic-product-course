"""Portable fixtures and CLI execution; no optional service dependencies."""

import json
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


def valid_labels(**overrides):
    """Return fresh, explicit values checked against the real genome.json."""
    labels = {
        "relevant": "yes",
        "g1_user": ["confider"],
        "g2_motive": ["companionship"],
        "g3_relation": ["friend"],
        "g4_investment": "regular",
        "g5_touchpoint": ["memory"],
        "g6_subtouch": ["memory.cross_session"],
        "g7_trigger": ["daily"],
        "g8_emotion": "disappointed",
        "g8_intensity": 2,
        "g9_voice_type": "problem",
        "g10_stage": "ongoing",
        "g11_value": ["not_alone"],
        "g12_competitor": ["none"],
        "g13_expected": "Agent 应当记住前一轮对话。",
        "g14_capability": ["cap.memory"],
        "g15_solvable": "agent",
        "g16_severity": "p1",
        "g17_risk": [],
    }
    labels.update(overrides)
    return labels


def write_jsonl(path, rows):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def read_jsonl(path):
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]


def run_cli(script, *args, cwd):
    # -S excludes site-packages; -B prevents bytecode writes outside tests/.
    return subprocess.run(
        [sys.executable, "-B", "-S", str(ROOT / script), *map(str, args)],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=30,
        check=False,
    )


def assert_success(test, result):
    test.assertEqual(result.returncode, 0, result.stdout + result.stderr)
