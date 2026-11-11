#!/usr/bin/env python3
"""Check tracked working-tree files without printing matched private content."""

import ipaddress
import os
from pathlib import Path
import re
import subprocess


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


def main():
    try:
        root = Path(os.fsdecode(subprocess.check_output(
            ["git", "rev-parse", "--show-toplevel"], stderr=subprocess.PIPE
        )).rstrip("\n"))
        tracked = subprocess.check_output(
            ["git", "ls-files", "-z"], cwd=root, stderr=subprocess.PIPE
        )
    except (OSError, subprocess.CalledProcessError):
        print("privacy: unable to list tracked files")
        return 1

    problems = 0
    exempt_lines = 0
    for entry in tracked.split(b"\0"):
        if not entry:
            continue
        name = os.fsdecode(entry)
        if name.startswith(FORBIDDEN_PREFIXES) or Path(name).name == ".env":
            print(f"{name}:1:forbidden-tracked-path")
            problems += 1
        try:
            data = (root / name).read_bytes()
        except OSError:
            print(f"{name}:0:read-error")
            problems += 1
            continue
        # NUL is Git's usual binary indicator; retain ASCII in non-UTF-8 text.
        if b"\0" in data:
            continue
        for number, line in enumerate(data.decode("utf-8", errors="surrogateescape").splitlines(), 1):
            if ALLOW.search(line):
                exempt_lines += 1
                continue
            for category in categories(line):
                print(f"{name}:{number}:{category}")
                problems += 1

    print(f"privacy: exempt lines: {exempt_lines}")
    if problems:
        print(f"privacy: FAIL ({problems} findings)")
        return 1
    print("privacy: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
