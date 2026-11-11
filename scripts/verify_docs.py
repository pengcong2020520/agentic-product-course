#!/usr/bin/env python3
"""Check tracked Markdown links and the annotation genome's consistency."""

import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit


# Inline destinations, including angle brackets, escapes, and parenthesized names.
LINK = re.compile(
    r"\[(?:\\.|[^\]\\])*\]\(\s*"
    r"(?P<target><[^>\n]*>|(?:\\.|[^\s()\\]|\((?:\\.|[^()\\])*\))*)"
    r"(?:\s+(?:\"[^\"\n]*\"|'[^'\n]*'|\([^()\n]*\)))?\s*\)"
)
VERSION = re.compile(r"^#\s+.*?\bv([0-9]+(?:\.[0-9]+)+)(?![\w.])")
GENOME = "pipeline/label/genome.json"


def mask_code(content):
    """Hide fenced blocks and code spans without moving any source positions."""
    def blank(text):
        return re.sub(r"[^\n]", " ", text)

    # Consume escapes outside spans; a closing run must match the opening length.
    spans = re.compile(r"\\[^\n]|(?<!`)(?P<ticks>`+)(?!`)[\s\S]*?(?<!`)(?P=ticks)(?!`)")

    def mask_spans(text):
        return spans.sub(lambda m: blank(m.group()) if m.group("ticks") else m.group(), text)

    result = []
    prose = []
    fence = None
    for line in content.splitlines(keepends=True):
        if fence is not None:
            result.append(blank(line))
            if re.fullmatch(r" {0,3}" + re.escape(fence[0]) +
                            r"{" + str(len(fence)) + r",}[ \t]*\n?", line):
                fence = None
            continue
        opening = re.match(r"^ {0,3}(`{3,}|~{3,})(.*)", line)
        if opening and not (opening[1][0] == "`" and "`" in opening[2]):
            result.append(mask_spans("".join(prose)))
            prose.clear()
            fence = opening[1]
            result.append(blank(line))
        else:
            prose.append(line)
    result.append(mask_spans("".join(prose)))
    return "".join(result)


def check_links(root, names):
    problems = []
    for name in names:
        if not name.endswith(".md"):
            continue
        source = root / name
        try:
            content = source.read_text(encoding="utf-8")
        except (OSError, UnicodeError):
            problems.append(f"{name}: cannot read Markdown")
            continue
        for match in LINK.finditer(mask_code(content)):
            target = match.group("target")
            if target.startswith("<"):
                target = target[1:-1]
            target = re.sub(r"\\([!\"#$%&'()*+,\-./:;<=>?@\[\]\\^_`{|}~])", r"\1", target)
            number = content.count("\n", 0, match.start()) + 1
            try:
                link = urlsplit(target)
            except ValueError:
                problems.append(f"{name}:{number}: invalid link: {target}")
                continue
            if link.scheme or link.netloc or link.path.startswith("/"):
                continue
            # An anchor-only link refers to this document; anchor validity is out of scope.
            if link.path and not (source.parent / unquote(link.path)).exists():
                problems.append(f"{name}:{number}: missing link target: {target}")
    return problems


def check_genome(root):
    problems = []
    try:
        genome = json.loads((root / GENOME).read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError):
        return [f"{GENOME}: cannot read genome JSON"]
    try:
        spec = genome["spec"]
        with (root / spec).open(encoding="utf-8") as document:
            title = document.readline().rstrip("\n")
        match = VERSION.search(title)
        if not match:
            problems.append(f"{spec}:1: missing version in first-line heading")
        elif genome["version"] != match.group(1):
            problems.append(
                f"{GENOME}: version {genome['version']} differs from {spec}:1: {match.group(1)}"
            )
    except (OSError, UnicodeError, ValueError, KeyError, TypeError):
        problems.append(f"{GENOME}: cannot read genome version or its spec document")

    try:
        genes = genome["genes"]
        by_id = {}
        for gene in genes:
            gene_id = gene["id"]
            if gene_id in by_id:
                problems.append(f"{GENOME}: duplicate gene id: {gene_id}")
            by_id[gene_id] = gene
        parents = by_id["g5_touchpoint"]["values"]
        for value in by_id["g6_subtouch"]["values"]:
            if value.split(".", 1)[0] not in parents:
                problems.append(f"{GENOME}: g6_subtouch value has unknown g5_touchpoint prefix: {value}")
    except (KeyError, TypeError, AttributeError):
        problems.append(f"{GENOME}: cannot check gene ids or touchpoint values")
    return problems


def main():
    try:
        root = Path(os.fsdecode(subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], stderr=subprocess.PIPE
        )).rstrip("\n"))
        tracked = subprocess.check_output(
            ["git", "ls-files", "-z"], cwd=root, stderr=subprocess.PIPE
        )
    except (OSError, subprocess.CalledProcessError):
        print("verify_docs: unable to list tracked files")
        return 1
    names = [os.fsdecode(entry) for entry in tracked.split(b"\0") if entry]
    problems = check_links(root, names) + check_genome(root)
    if problems:
        for problem in problems:
            print(problem)
        return 1
    print("verify_docs: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
