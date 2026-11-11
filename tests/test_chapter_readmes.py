"""Enforce chapter skeletons, verbatim excerpts, and compilable entry points."""

import ast
from pathlib import Path
import py_compile
import re

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _without_indent(line, indent):
    # Empty lines have no indentation; preserve every other character exactly.
    if not line:
        return line
    if line.startswith(indent):
        return line[len(indent):]
    return None


def _assert_excerpt_matches(chapter, block_number, lines, source):
    while lines and not lines[0].strip():
        lines = lines[1:]
    while lines and not lines[-1].strip():
        lines = lines[:-1]
    segments = [[]]
    for line in lines:
        if line.strip() == '...':
            segments.append([])
        else:
            segments[-1].append(line)
    segments = [segment for segment in segments if segment]
    excerpt = [line for segment in segments for line in segment]
    anchor = next((line for line in excerpt if line.strip()), None)
    if anchor is None:
        return

    # Infer a single indentation adjustment for the entire block, including
    # all ellipsis-separated segments. Never strip individual lines freely.
    indents = {('', '')}
    for line in source:
        if line.lstrip(' \t') != anchor.lstrip(' \t'):
            continue
        if line.endswith(anchor):
            indents.add(('', line[:len(line) - len(anchor)]))
        if anchor.endswith(line):
            indents.add((anchor[:len(anchor) - len(line)], ''))

    best_progress = 0
    for readme_indent, source_indent in indents:
        expected = [[_without_indent(line, readme_indent) for line in segment]
                    for segment in segments]
        if any(line is None for segment in expected for line in segment):
            continue
        actual = [_without_indent(line, source_indent) for line in source]
        cursor = progress = 0
        for segment in expected:
            for start in range(cursor, len(actual)):
                matched = 0
                for wanted, found in zip(segment, actual[start:start + len(segment)]):
                    if wanted != found:
                        break
                    matched += 1
                best_progress = max(best_progress, progress + matched)
                if matched == len(segment):
                    cursor = start + matched
                    progress += matched
                    break
            else:
                break
        else:
            return

    raise AssertionError(
        f'{chapter.name}: README.md Python 代码块 #{block_number}: '
        f'第一行不匹配: {excerpt[best_progress]!r}'
    )


def _check_chapter_excerpts(chapter):
    text = (chapter / 'README.md').read_text(encoding='utf-8')
    section = re.search(r'^## 工作原理[ \t]*\n(.*?)(?=^## |\Z)',
                        text, re.MULTILINE | re.DOTALL)
    if section is None:
        return
    source = (chapter / 'code.py').read_text(encoding='utf-8').splitlines()
    # Consume other fenced blocks too, so their contents cannot be mistaken
    # for Python fences. HTML details wrappers need no special treatment.
    fences = re.finditer(r'^[ \t]*```([^\n]*)\n(.*?)^[ \t]*```[ \t]*$',
                         section.group(1), re.MULTILINE | re.DOTALL)
    block_number = 0
    for fence in fences:
        if fence.group(1).strip() == 'python':
            block_number += 1
            _assert_excerpt_matches(chapter, block_number,
                                    fence.group(2).splitlines(), source)


def test_chapter_readme_python_excerpts():
    for readme in sorted(ROOT.glob('s[0-9][0-9]_*/README.md')):
        _check_chapter_excerpts(readme.parent)


def _fake_chapter(tmp_path, code, blocks):
    chapter = tmp_path / 's01_example'
    chapter.mkdir()
    (chapter / 'code.py').write_text(code, encoding='utf-8')
    (chapter / 'README.md').write_text(
        '## 解决方案\n```python\nignored_before()\n```\n'
        '## 工作原理\n```text\nignored_non_python()\n```\n'
        + '\n'.join(f'<details>\n```python\n{block}\n```\n</details>'
                    for block in blocks)
        + '\n## 试一下\n```python\nignored_after()\n```\n',
        encoding='utf-8',
    )
    return chapter


def test_excerpt_exact_match(tmp_path):
    chapter = _fake_chapter(tmp_path, 'before()\nfirst()\nsecond()\nafter()\n',
                            ['\nfirst()\nsecond()\n', 'after()'])
    _check_chapter_excerpts(chapter)


def test_excerpt_common_indent_removed(tmp_path):
    chapter = _fake_chapter(
        tmp_path, 'def run():\n    if ready:\n        work()\n    done()\n',
        ['if ready:\n    work()\ndone()',
         '        if ready:\n            work()\n        done()'],
    )
    _check_chapter_excerpts(chapter)


def test_excerpt_ellipsis_segments_in_order(tmp_path):
    chapter = _fake_chapter(
        tmp_path, 'def run():\n    first()\n    skipped()\n    last()\n',
        ['first()\n...\nlast()'],
    )
    _check_chapter_excerpts(chapter)


@pytest.mark.parametrize('changed_line', ['Second()', 'second( )', 'second() ', ' second()'])
def test_excerpt_changed_character_fails(tmp_path, changed_line):
    chapter = _fake_chapter(tmp_path, 'first()\nsecond()\n',
                            ['first()', f'first()\n{changed_line}'])
    with pytest.raises(AssertionError) as error:
        _check_chapter_excerpts(chapter)
    assert str(error.value) == (
        f's01_example: README.md Python 代码块 #2: 第一行不匹配: {changed_line!r}'
    )


def test_excerpt_reversed_segments_fail(tmp_path):
    chapter = _fake_chapter(tmp_path, 'first()\nlast()\n',
                            ['last()\n...\nfirst()'])
    with pytest.raises(AssertionError) as error:
        _check_chapter_excerpts(chapter)
    assert str(error.value) == (
        "s01_example: README.md Python 代码块 #1: 第一行不匹配: 'first()'"
    )


def test_chapter_readmes(tmp_path):
    chapters = sorted(p for p in ROOT.glob('s[0-9][0-9]_*') if p.is_dir())
    assert len(chapters) == 6
    assert [p.name[:3] for p in chapters] == [f's{i:02d}' for i in range(1, 7)]
    for chapter in chapters:
        readme, code = chapter / 'README.md', chapter / 'code.py'
        assert readme.is_file()
        assert code.is_file()
        text = readme.read_text(encoding='utf-8')
        lines = text.splitlines()
        assert re.match(r'^# s\d\d: .+ — .+$', lines[0])
        navigation = lines[2].split(' → ')
        assert len(navigation) == 6
        for other, item in zip(chapters, navigation):
            number = other.name[:3]
            if other == chapter:
                assert item == f'`{number}`'
            elif chapters.index(other) == chapters.index(chapter) + 1:
                assert item == f'[{number}](../{other.name}/)'
            else:
                assert item == number
        assert re.search(r'^> \*".+"\* — .+。$', text, re.MULTILINE)
        assert re.search(r'^> \*\*[^*\n]+层\*\*：.+', text, re.MULTILINE)
        headings = re.findall(r'^## (.+)$', text, re.MULTILINE)
        assert headings == ['问题', '解决方案', '工作原理', '试一下', '接下来']
        py_compile.compile(str(code), cfile=str(tmp_path / f'{chapter.name}.pyc'), doraise=True)
        doc = ast.get_docstring(ast.parse(code.read_text(encoding='utf-8')))
        assert doc and chapter.name in doc and 'Usage:' in doc


def test_check_implementations_match():
    definitions = []
    for chapter in ('s03_product_genome', 's04_labeling', 's05_agreement'):
        tree = ast.parse((ROOT / chapter / 'code.py').read_text(encoding='utf-8'))
        check = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'check')
        definitions.append(ast.dump(check, include_attributes=False))
    assert definitions[0] == definitions[1] == definitions[2]
