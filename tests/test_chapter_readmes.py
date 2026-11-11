"""Enforce chapter skeletons and compile each independent entry point."""

import ast
from pathlib import Path
import py_compile
import re

ROOT = Path(__file__).resolve().parents[1]


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
