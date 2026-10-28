#!/usr/bin/env python3
"""GORE DRAFT download numbers, from GitHub's own release counters.

    python tools/stats.py

Shows downloads per version and per file (Windows installer, portable zip,
Linux), plus totals. Uses only the standard library and GitHub's public API,
so it needs no login for a public repository. GitHub allows about 60
unauthenticated requests an hour, which is plenty for this.

For page views and visitors, see the repo's Insights -> Traffic tab on
github.com. Only you can see that, and it keeps the last 14 days.
"""
import json
import sys
import urllib.request

REPO = "splattervhs/GoreDraft"


def kind(name: str) -> str:
    n = name.lower()
    if n.endswith(".exe"):
        return "Windows installer"
    if "portable" in n:
        return "Windows portable"
    if "linux" in n:
        return "Linux / Chromebook"
    return "Other"


def main():
    url = f"https://api.github.com/repos/{REPO}/releases?per_page=100"
    req = urllib.request.Request(url, headers={"Accept": "application/vnd.github+json",
                                               "User-Agent": "goredraft-stats"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            releases = json.load(r)
    except Exception as e:  # noqa: BLE001
        sys.exit(f"Couldn't reach GitHub: {e}\n(Is the repo public and online?)")
    if not releases:
        print("No releases published yet.")
        return
    total = 0
    by_kind = {}
    print(f"\nGORE DRAFT downloads ({REPO})\n" + "=" * 52)
    for rel in releases:
        status = " (draft)" if rel.get("draft") else (" (beta)" if rel.get("prerelease") else "")
        rel_total = sum(a["download_count"] for a in rel["assets"])
        total += rel_total
        print(f"\n{rel['tag_name']}{status}  ·  {rel_total:,} downloads  ·  "
              f"{(rel.get('published_at') or 'unpublished')[:10]}")
        for a in sorted(rel["assets"], key=lambda a: -a["download_count"]):
            k = kind(a["name"])
            by_kind[k] = by_kind.get(k, 0) + a["download_count"]
            print(f"   {a['download_count']:>7,}  {k:<20} {a['name']}")
    print("\n" + "=" * 52)
    for k, n in sorted(by_kind.items(), key=lambda kv: -kv[1]):
        print(f"   {n:>7,}  {k}")
    print(f"   {total:>7,}  TOTAL\n")
    print("Page views and visitors: github.com/" + REPO + "/graphs/traffic\n")


if __name__ == "__main__":
    main()
