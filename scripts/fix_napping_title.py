#!/usr/bin/env python3
"""
One-shot cleanup: fix the truncated title for the napping post in
blog/index.html and blog/rss.xml.

The post HTML itself was already fixed manually. This patches the two
auto-generated artifacts (index card + RSS item) that still carry the
stale truncated title from the original publish run.

Safe to run multiple times — idempotent. Does nothing if the bad title
is already gone.

Usage (from repo root):
    python3 scripts/fix_napping_title.py
"""

import os
import sys

OLD_TITLE = "Daytime Napping and Mortality Risk: What Older..."
NEW_TITLE = "Daytime Napping and Mortality Risk: What This Means for Adults Over 50"

# RSS uses a slightly different escape situation — same string, but RSS
# title doesn't need HTML escaping for these chars, so the literal match
# works for both files.

FILES_TO_PATCH = [
    "blog/index.html",
    "blog/rss.xml",
]


def patch_file(path: str) -> bool:
    """Replace OLD_TITLE with NEW_TITLE in `path`. Returns True if changed."""
    if not os.path.exists(path):
        print(f"  ⚠ {path} not found — skipping")
        return False

    with open(path, "r", encoding="utf-8") as f:
        content = f.read()

    occurrences = content.count(OLD_TITLE)
    if occurrences == 0:
        print(f"  ✓ {path}: already clean (no truncated title found)")
        return False

    new_content = content.replace(OLD_TITLE, NEW_TITLE)
    with open(path, "w", encoding="utf-8") as f:
        f.write(new_content)

    print(f"  ✅ {path}: replaced {occurrences} occurrence(s)")
    return True


def main():
    print("Fixing truncated napping-post title in auto-generated files...")
    print(f"  Old: {OLD_TITLE!r}")
    print(f"  New: {NEW_TITLE!r}\n")

    changed_any = False
    for path in FILES_TO_PATCH:
        if patch_file(path):
            changed_any = True

    print()
    if changed_any:
        print("Done. Commit and push:")
        print("  git add blog/index.html blog/rss.xml")
        print("  git commit -m 'fix: replace truncated napping-post title in index and RSS'")
        print("  git push")
    else:
        print("No changes needed. All files already clean.")


if __name__ == "__main__":
    main()
