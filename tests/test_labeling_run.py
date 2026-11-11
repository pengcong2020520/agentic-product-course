"""Check runner boundaries without invoking logged-in model CLIs."""

from contextlib import redirect_stdout
import io
from pathlib import Path
import shlex
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

from s04_labeling import code as labeling
from tests._support import read_jsonl, valid_labels, write_jsonl


def invoke(directory, jobs=2, dry_run=False):
    output = io.StringIO()
    args = SimpleNamespace(directory=str(directory), annotators='codex,grok', jobs=jobs, dry_run=dry_run)
    with redirect_stdout(output):
        labeling.run(args, None)
    return output.getvalue()


def prepare(tmp_path, monkeypatch, count=2):
    # run() resolves paths from the repo root, just as the shell did.
    monkeypatch.chdir(Path.cwd())
    monkeypatch.delenv('GENE', raising=False)
    monkeypatch.setenv('CODEX_BIN', 'codex-fixture')
    monkeypatch.setenv('GROK_BIN', 'grok-fixture')
    for number in range(count):
        write_jsonl(tmp_path / 'chunks' / f'chunk-{number:02d}.jsonl', [{'id': str(number)}])


def test_dry_run_commands_and_no_writes(tmp_path, monkeypatch):
    prepare(tmp_path, monkeypatch)
    before = sorted(tmp_path.rglob('*'))
    with patch.object(labeling.subprocess, 'run') as cli:
        output = invoke(tmp_path, dry_run=True)
    cli.assert_not_called()
    assert sorted(tmp_path.rglob('*')) == before
    lines = output.splitlines()
    assert len(lines) == 4
    assert shlex.split(lines[0]) == [
        'codex-fixture', 'exec', '-C', str(Path(__file__).resolve().parents[1]),
        '-s', 'workspace-write', '-o', str(tmp_path / 'logs/codex-chunk-00.final.md'), '-',
        '<', str(tmp_path / 'briefs/codex-chunk-00.md'),
        '>', str(tmp_path / 'logs/codex-chunk-00.log'), '2>&1',
    ]
    assert lines[1].startswith('grok-fixture -p "$(cat ')
    assert '--always-approve --cwd ' in lines[1]
    assert '--disable-web-search > ' in lines[1]


def test_completed_skipped_invalid_retried_even_in_dry_run(tmp_path, monkeypatch):
    prepare(tmp_path, monkeypatch, count=1)
    write_jsonl(tmp_path / 'codex/chunk-00.jsonl', [{'id': '0', **valid_labels()}])
    write_jsonl(tmp_path / 'grok/chunk-00.jsonl', [{'id': 'wrong', **valid_labels()}])
    output = invoke(tmp_path, dry_run=True)
    assert '跳过 codex chunk-00（已完成且校验通过）' in output
    assert 'codex-fixture exec' not in output
    assert 'grok-fixture -p' in output


def test_gene_mode_cli_parameters_logs_briefs_resume_and_concurrency(tmp_path, monkeypatch):
    prepare(tmp_path, monkeypatch, count=3)
    monkeypatch.setenv('GENE', 'g17_risk')
    calls = []
    active = peak = 0
    lock = threading.Lock()

    def cli(command, **kwargs):
        nonlocal active, peak
        with lock:
            active += 1
            peak = max(peak, active)
        try:
            text = kwargs['stdin'].read() if command[0] == 'codex-fixture' else command[2]
            log_path = Path(kwargs['stdout'].name)
            stem = log_path.stem
            who = stem.split('-', 1)[0]
            number = stem.rsplit('-', 1)[1]
            assert kwargs['cwd'] == Path(__file__).resolve().parents[1]
            assert kwargs['stderr'] == labeling.subprocess.STDOUT
            assert kwargs['check'] is False
            assert {key: kwargs['env'][key] for key in ('DIR', 'CODEX_BIN', 'GROK_BIN', 'GENE', 'PWD')} == {
                'DIR': str(tmp_path), 'CODEX_BIN': 'codex-fixture', 'GROK_BIN': 'grok-fixture',
                'GENE': 'g17_risk', 'PWD': str(kwargs['cwd']),
            }
            if who == 'codex':
                assert command == ['codex-fixture', 'exec', '-C', str(kwargs['cwd']),
                                   '-s', 'workspace-write', '-o',
                                   str(tmp_path / 'logs' / f'{stem}.final.md'), '-']
            else:
                assert command == ['grok-fixture', '-p', text, '--always-approve',
                                   '--cwd', str(kwargs['cwd']), '--disable-web-search']
                assert kwargs['stdin'] is None
            expected = Path(labeling.__file__).with_name('gene-brief.md').read_text(encoding='utf-8')
            out = tmp_path / f'{who}-g17_risk' / f'chunk-{number}.jsonl'
            expected = expected.replace('{IN}', str(tmp_path / 'chunks' / f'chunk-{number}.jsonl'))
            expected = expected.replace('{OUT}', str(out)).replace('{GENE}', 'g17_risk')
            assert text == (expected if who == 'codex' else expected.rstrip('\n'))
            assert (tmp_path / 'briefs' / f'{stem}.md').read_text(encoding='utf-8') == expected
            kwargs['stdout'].write('fixture log\n')
            write_jsonl(out, [{'id': str(int(number)), 'g17_risk': []}])
            time.sleep(0.02)
            with lock:
                calls.append(command)
            return SimpleNamespace(returncode=1)  # Nonzero CLI exits still validate outputs.
        finally:
            with lock:
                active -= 1

    with patch.object(labeling.subprocess, 'run', side_effect=cli):
        output = invoke(tmp_path)
        resumed = invoke(tmp_path)
    assert len(calls) == 6
    assert peak == 2
    assert output.count('：OK') == 6
    assert resumed.count('已完成且校验通过') == 6
    assert all(p.read_text(encoding='utf-8') == 'fixture log\n' for p in (tmp_path / 'logs').glob('*.log'))
    assert read_jsonl(tmp_path / 'codex-g17_risk/chunk-00.jsonl') == [{'id': '0', 'g17_risk': []}]
