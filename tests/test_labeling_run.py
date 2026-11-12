"""Check runner boundaries without invoking logged-in model CLIs."""

from contextlib import redirect_stdout
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import shlex
import threading
import time
from types import SimpleNamespace
from unittest.mock import patch

import pytest

from s04_labeling import code as labeling
from tests._support import read_jsonl, valid_labels, write_jsonl


def invoke(directory, jobs=2, dry_run=False, skip_preflight=False, annotators='codex,grok'):
    output = io.StringIO()
    args = SimpleNamespace(directory=str(directory), annotators=annotators, jobs=jobs,
                           dry_run=dry_run, skip_preflight=skip_preflight)
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


def preflight_reply(command, kwargs):
    """Handle only preflight calls; every other call remains a chunk invocation."""
    if command[1:] == ['--version']:
        return SimpleNamespace(returncode=0, stdout=f'{command[0]} 1.2.3\nextra version details\n')
    if Path(kwargs['stdout'].name).name != 'preflight.log':
        return None
    temporary = Path(kwargs['cwd'])
    assert temporary.is_dir()
    assert not (temporary / 'smoke.txt').exists()
    assert kwargs['stderr'] == labeling.subprocess.STDOUT
    assert kwargs['check'] is False
    if command[0] == 'codex-fixture':
        assert command == ['codex-fixture', 'exec', '-C', str(temporary), '-s',
                           'workspace-write', '--skip-git-repo-check', '-']
        prompt = kwargs['input']
    else:
        assert command == ['grok-fixture', '-p', command[2], '--always-approve', '--cwd', str(temporary)]
        assert kwargs['input'] is None
        prompt = command[2]
    assert 'smoke.txt' in prompt and 'ok' in prompt
    (temporary / 'smoke.txt').write_text('ok', encoding='utf-8')
    kwargs['stdout'].write('smoke succeeded\n')
    return SimpleNamespace(returncode=0)


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
        reply = preflight_reply(command, kwargs)
        if reply is not None:
            return reply
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
    assert all(p.read_text(encoding='utf-8') ==
               f'fixture log\n\n# annotator-version: {p.stem.split("-", 1)[0]}-fixture 1.2.3\n'
               for p in (tmp_path / 'logs').glob('*.log'))
    assert read_jsonl(tmp_path / 'codex-g17_risk/chunk-00.jsonl') == [{'id': '0', 'g17_risk': []}]


def test_preflight_success_before_any_chunks_and_run_metadata(tmp_path, monkeypatch):
    prepare(tmp_path, monkeypatch)
    monkeypatch.setenv('GENE', 'g17_risk')
    events = []
    temporary_dirs = []
    started = datetime.now(timezone.utc)

    def cli(command, **kwargs):
        reply = preflight_reply(command, kwargs)
        if reply is not None:
            events.append((command[0], 'version' if command[1:] == ['--version'] else 'smoke'))
            temporary_dirs.append(Path(kwargs['cwd']))
            return reply
        assert events[:4] == [('codex-fixture', 'version'), ('codex-fixture', 'smoke'),
                              ('grok-fixture', 'version'), ('grok-fixture', 'smoke')]
        assert (tmp_path / 'logs/run-meta.json').is_file()
        events.append((command[0], 'chunk'))
        kwargs['stdout'].write('chunk finished')
        return SimpleNamespace(returncode=0)

    with patch.object(labeling.subprocess, 'run', side_effect=cli):
        invoke(tmp_path)
    assert len(events) == 8
    assert all(not path.exists() for path in temporary_dirs)
    assert len(set(temporary_dirs)) == 2
    meta = json.loads((tmp_path / 'logs/run-meta.json').read_text(encoding='utf-8'))
    assert started <= datetime.fromisoformat(meta['started_at']) <= datetime.now(timezone.utc)
    assert meta == {
        'started_at': meta['started_at'], 'gene': 'g17_risk',
        'annotators': {
            'codex': {'bin': 'codex-fixture', 'version': 'codex-fixture 1.2.3'},
            'grok': {'bin': 'grok-fixture', 'version': 'grok-fixture 1.2.3'},
        },
    }
    logs = list((tmp_path / 'logs').glob('*.log'))
    assert len(logs) == 4
    for log in logs:
        who = log.stem.split('-', 1)[0]
        assert log.read_text(encoding='utf-8') == f'chunk finished\n# annotator-version: {who}-fixture 1.2.3\n'


@pytest.mark.parametrize('who', ['codex-fixture', 'grok-fixture'])
@pytest.mark.parametrize('failure', ['exit', 'missing', 'wrong', 'oserror', 'timeout'])
def test_preflight_failure_exits_two_without_dispatch(tmp_path, monkeypatch, capsys, who, failure):
    prepare(tmp_path, monkeypatch)
    calls = []
    failed_command = None

    def cli(command, **kwargs):
        nonlocal failed_command
        calls.append(command)
        if command[1:] == ['--version']:
            return preflight_reply(command, kwargs)
        assert Path(kwargs['stdout'].name).name == 'preflight.log', 'a chunk was dispatched'
        if command[0] != who:
            return preflight_reply(command, kwargs)
        failed_command = command
        kwargs['stdout'].write(''.join(f'log-{i:02d}\n' for i in range(25)))
        if failure == 'oserror':
            raise FileNotFoundError('missing host')
        if failure == 'timeout':
            raise labeling.subprocess.TimeoutExpired(command, 120)
        if failure in ('exit', 'wrong'):
            (Path(kwargs['cwd']) / 'smoke.txt').write_text('ok' if failure == 'exit' else 'wrong')
        return SimpleNamespace(returncode=1 if failure == 'exit' else 0)

    args = SimpleNamespace(directory=str(tmp_path), annotators='codex,grok', jobs=2,
                           dry_run=False, skip_preflight=False)
    with patch.object(labeling.subprocess, 'run', side_effect=cli), pytest.raises(SystemExit) as exc:
        labeling.run(args, None)
    assert exc.value.code == 2
    output = capsys.readouterr().out
    assert f'冒烟检查失败：{who.split("-", 1)[0]}' in output
    assert shlex.join(failed_command) in output
    assert output.split('日志末尾 20 行：\n')[1].splitlines() == [f'log-{i:02d}' for i in range(5, 25)]
    assert len(calls) == (2 if who == 'codex-fixture' else 4)
    assert not list((tmp_path / 'briefs').iterdir())
    assert not list((tmp_path / 'logs').glob('*chunk*'))
    assert not Path(failed_command[failed_command.index('-C') + 1] if who == 'codex-fixture'
                    else failed_command[-1]).exists()


def test_skip_preflight_dispatches_without_smoke_or_version_queries(tmp_path, monkeypatch):
    prepare(tmp_path, monkeypatch, count=1)
    calls = []

    def cli(command, **kwargs):
        assert command[1:] != ['--version']
        assert 'chunk-00' in Path(kwargs['stdout'].name).name
        calls.append(command)
        return SimpleNamespace(returncode=0)

    with patch.object(labeling.subprocess, 'run', side_effect=cli):
        invoke(tmp_path, skip_preflight=True)
    assert len(calls) == 2
    meta = json.loads((tmp_path / 'logs/run-meta.json').read_text(encoding='utf-8'))
    assert meta['gene'] == ''
    assert meta['annotators'] == {
        'codex': {'bin': 'codex-fixture', 'version': 'unknown'},
        'grok': {'bin': 'grok-fixture', 'version': 'unknown'},
    }
    assert all(log.read_text(encoding='utf-8') == '\n# annotator-version: unknown\n'
               for log in (tmp_path / 'logs').glob('*.log'))


def test_skip_preflight_parser_option(tmp_path, monkeypatch):
    prepare(tmp_path, monkeypatch, count=1)
    monkeypatch.setattr('sys.argv', ['code.py', 'run', str(tmp_path), 'codex', '--skip-preflight'])
    with patch.object(labeling.subprocess, 'run', return_value=SimpleNamespace(returncode=0)) as cli:
        labeling.main()
    cli.assert_called_once()
    assert cli.call_args.args[0][1] == 'exec'


@pytest.mark.parametrize('failure', ['exit', 'empty', 'oserror', 'timeout'])
def test_version_query_failure_exits_two_without_dispatch(tmp_path, monkeypatch, capsys, failure):
    prepare(tmp_path, monkeypatch)

    def cli(command, **kwargs):
        assert command == ['codex-fixture', '--version']
        if failure == 'oserror':
            raise FileNotFoundError('missing executable')
        if failure == 'timeout':
            raise labeling.subprocess.TimeoutExpired(command, 15)
        return SimpleNamespace(returncode=1 if failure == 'exit' else 0,
                               stdout='version failed\n' if failure == 'exit' else '')

    args = SimpleNamespace(directory=str(tmp_path), annotators='codex,grok', jobs=2,
                           dry_run=False, skip_preflight=False)
    with patch.object(labeling.subprocess, 'run', side_effect=cli) as mocked, pytest.raises(SystemExit) as exc:
        labeling.run(args, None)
    assert exc.value.code == 2
    mocked.assert_called_once()
    output = capsys.readouterr().out
    assert '冒烟检查失败：codex' in output
    assert 'codex-fixture --version' in output
    assert '日志末尾 20 行：' in output
    assert not list((tmp_path / 'briefs').iterdir())
    assert not list((tmp_path / 'logs').glob('*chunk*'))


def test_preflight_only_selected_annotator_once(tmp_path, monkeypatch):
    prepare(tmp_path, monkeypatch, count=3)
    preflight_calls = []
    chunks = []

    def cli(command, **kwargs):
        assert command[0] == 'grok-fixture'
        reply = preflight_reply(command, kwargs)
        if reply is not None:
            preflight_calls.append(command)
            return reply
        chunks.append(command)
        return SimpleNamespace(returncode=0)

    with patch.object(labeling.subprocess, 'run', side_effect=cli):
        invoke(tmp_path, annotators='grok')
    assert len(preflight_calls) == 2  # One version query and one smoke task.
    assert len(chunks) == 3
    meta = json.loads((tmp_path / 'logs/run-meta.json').read_text(encoding='utf-8'))
    assert meta['annotators'] == {'grok': {'bin': 'grok-fixture', 'version': 'grok-fixture 1.2.3'}}
