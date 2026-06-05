#!/usr/bin/env python3
"""Compare two Pyodide package indices and show added/removed packages.

Usage:
    python compare_pyodide_index.py 0.28.3 0.29.4
"""

import sys
import urllib.request
from html.parser import HTMLParser

BASE_URL = "https://index.pyodide.org/"


class AnchorTextParser(HTMLParser):
    def __init__(self):
        super().__init__()
        self.packages: set[str] = set()
        self._in_anchor = False

    def handle_starttag(self, tag, attrs):
        if tag == "a":
            self._in_anchor = True

    def handle_endtag(self, tag):
        if tag == "a":
            self._in_anchor = False

    def handle_data(self, data):
        if self._in_anchor:
            name = data.strip()
            if name:
                self.packages.add(name)


def fetch_packages(version: str) -> set[str]:
    url = f"{BASE_URL}{version}"
    req = urllib.request.Request(
        url, headers={"User-Agent": "compare-pyodide-index/1.0"}
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        html = resp.read().decode()
    parser = AnchorTextParser()
    parser.feed(html)
    return parser.packages


def main():
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} <old_version> <new_version>", file=sys.stderr)
        sys.exit(1)

    old_ver, new_ver = sys.argv[1], sys.argv[2]

    print(f"Fetching index for {old_ver}...", file=sys.stderr)
    old_pkgs = fetch_packages(old_ver)
    print(f"  {len(old_pkgs)} packages", file=sys.stderr)

    print(f"Fetching index for {new_ver}...", file=sys.stderr)
    new_pkgs = fetch_packages(new_ver)
    print(f"  {len(new_pkgs)} packages", file=sys.stderr)
    print(file=sys.stderr)

    removed = sorted(old_pkgs - new_pkgs)
    added = sorted(new_pkgs - old_pkgs)

    if removed:
        print(f"Removed ({len(removed)}):")
        for p in removed:
            print(f"  - {p}")
    else:
        print("Removed: (none)")

    print()

    if added:
        print(f"Added ({len(added)}):")
        for p in added:
            print(f"  + {p}")
    else:
        print("Added: (none)")


if __name__ == "__main__":
    main()
