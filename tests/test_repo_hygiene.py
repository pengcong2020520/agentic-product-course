"""Repository privacy, Markdown destinations, and genome consistency."""

import ipaddress
import json
import os
from pathlib import Path
import re
import subprocess
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]


LOCAL_PATH = re.compile(r"/(?:Users|home)/([^/\s]+)/")
EMAIL = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)+")
IPV4 = re.compile(r"(?<![A-Za-z0-9.])(?:[0-9]{1,3}\.){3}[0-9]{1,3}(?![A-Za-z0-9.])")
SECRET = re.compile(
    r"sk-[A-Za-z0-9]{20,}|ghp[_]|github_pat[_]|AKIA[0-9A-Z]{16}"
    r"|-----BEGIN "
    r"[^\r\n]*PRIVATE KEY-----"
)
ALLOW = re.compile(r"# privacy: allow\s*$")
FORBIDDEN_PREFIXES = ("data/", ".private/", "agentic-product-course/", ".worktrees/")
ALLOWED_NETWORKS = tuple(
    ipaddress.IPv4Network(network)
    for network in ("127.0.0.0/8", "10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16")
)


def categories(line):
    """Return each matching category once per line, using explicit allowlists."""
    if any(match.group() != "/home/codex/" for match in LOCAL_PATH.finditer(line)):
        yield "local-absolute-path"
    for match in EMAIL.finditer(line):
        address = match.group().lower()
        if address != "noreply@anthropic.com" and address.rsplit("@", 1)[1] not in {
            "example.com", "example.org"
        }:
            yield "email"
            break
    for match in IPV4.finditer(line):
        try:
            address = ipaddress.IPv4Address(match.group())
        except ipaddress.AddressValueError:
            continue
        if int(address) != 0 and not any(address in network for network in ALLOWED_NETWORKS):
            yield "public-ipv4"
            break
    if SECRET.search(line):
        yield "secret"



# Inline destinations, including angle brackets, escapes, and parenthesized names.
LINK = re.compile(
    r"\[(?:\\.|[^\]\\])*\]\(\s*"
    r"(?P<target><[^>\n]*>|(?:\\.|[^\s()\\]|\((?:\\.|[^()\\])*\))*)"
    r"(?:\s+(?:\"[^\"\n]*\"|'[^'\n]*'|\([^()\n]*\)))?\s*\)"
)
VERSION = re.compile(r"^#\s+.*?\bv([0-9]+(?:\.[0-9]+)+)(?![\w.])")
GENOME = "s03_product_genome/genome.json"


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



def working_tree_names(root):
    # Include untracked migration files before staging; exclude removed old paths.
    tracked = subprocess.check_output(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"], cwd=root
    )
    deleted = set(subprocess.check_output(
        ["git", "ls-files", "--deleted", "-z"], cwd=root
    ).split(b"\0"))
    return sorted({os.fsdecode(entry) for entry in tracked.split(b"\0")
                   if entry and entry not in deleted})


def privacy_problems(root, names):
    problems = []
    for name in names:
        if name.startswith(FORBIDDEN_PREFIXES) or Path(name).name == ".env":
            problems.append(f"{name}:1:forbidden-tracked-path")
        try:
            data = (root / name).read_bytes()
        except OSError:
            problems.append(f"{name}:0:read-error")
            continue
        if b"\0" in data:
            continue
        for number, line in enumerate(data.decode("utf-8", errors="surrogateescape").splitlines(), 1):
            if ALLOW.search(line):
                continue
            problems.extend(f"{name}:{number}:{category}" for category in categories(line))
    return problems


def test_repository_privacy():
    assert privacy_problems(ROOT, working_tree_names(ROOT)) == []


def test_markdown_links():
    assert check_links(ROOT, working_tree_names(ROOT)) == []


def test_genome_consistency():
    assert check_genome(ROOT) == []
    genome = json.loads((ROOT / GENOME).read_text(encoding="utf-8"))
    assert genome["spec"] == "s03_product_genome/genome.md"
