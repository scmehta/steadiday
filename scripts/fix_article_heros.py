#!/usr/bin/env python3
“””
fix_article_heros.py
Surgical hero-image fixes for the four blog articles where
search_hero_image() failed in different ways:

- Default fallback (abstract teal gradient)
- LLM-hallucinated Unsplash URL (likely 404)
- Wrong-category image from a fallback path

Each fix replaces the hero <img src>, plus the og:image and twitter:image
meta tags (which use the same URL) and the JSON-LD schema image, so
the page banner and social-share previews all update together.

Idempotent: if the old URL is already gone, the script reports it and
makes no change. Safe to re-run.

Run from the repo root:
python fix_article_heros.py
“””

from pathlib import Path

BLOG_DIR = Path(“blog”)

# (filename, old_hero_url, new_hero_url, reason)

FIXES = [
(
“2026-05-04-athome-alzheimers-injection-whats-coming.html”,
“https://images.unsplash.com/photo-1557683316-973673baf926?w=1200&q=80”,
“https://images.unsplash.com/photo-1503676260728-1c00da094a0b?w=1200&q=80”,
“DEFAULT_HERO fallback (abstract teal) -> brain imagery”,
),
(
“2026-04-23-testosterone-therapy-for-men-over.html”,
“https://images.unsplash.com/photo-nUQIh8RH2XQ?w=1200&q=80”,
“https://images.unsplash.com/photo-1538805060514-97d9cc17730c?w=1200&q=80”,
“BROKEN URL (LLM hallucination, likely 404) -> active senior man”,
),
(
“2026-04-20-vitamin-d-your-midlife-brain.html”,
“https://images.unsplash.com/photo-1475924156734-496f6cac6ec1?w=1200&q=80”,
“https://images.unsplash.com/photo-1502082553048-f009c37129b9?w=1200&q=80”,
“generic morning mist -> sunlit forest (vitamin D from sun)”,
),
(
“2026-04-18-your-smile-after-50-a.html”,
“https://images.unsplash.com/photo-1541781774459-bb2af2f05b55?w=1200&q=80”,
“https://images.unsplash.com/photo-1494790108377-be9c29b29330?w=1200&q=80”,
“wrong-topic bedroom photo -> smiling person”,
),
]

def fix_file(path: Path, old_url: str, new_url: str) -> int:
“”“Replace old_url with new_url in path. Handles both raw `&`
and `&amp;` encodings so it works regardless of how the source
HTML was written. Returns total replacement count.”””
content = path.read_text(encoding=“utf-8”)
old_amp = old_url.replace(”&”, “&”)
new_amp = new_url.replace(”&”, “&”)

```
n_raw = content.count(old_url)
n_amp = content.count(old_amp)
if n_raw == 0 and n_amp == 0:
    return 0

if n_raw:
    content = content.replace(old_url, new_url)
if n_amp:
    content = content.replace(old_amp, new_amp)
path.write_text(content, encoding="utf-8")
return n_raw + n_amp
```

def main():
print(”=” * 68)
print(“Fixing article hero images”)
print(”=” * 68)
total_changes = 0
for filename, old, new, reason in FIXES:
path = BLOG_DIR / filename
if not path.exists():
print(f”  [skip] {filename}: file not found”)
continue
n = fix_file(path, old, new)
if n:
total_changes += n
print(f”  [ok]   {filename}”)
print(f”         {reason}”)
print(f”         {n} replacement{‘s’ if n != 1 else ‘’}”)
else:
print(f”  [info] {filename}: old URL not present (already fixed)”)
print(”=” * 68)
print(f”Done. {total_changes} total replacement(s) across {len(FIXES)} files.”)
print(“Verify with `git diff blog/` before committing.”)

if **name** == “**main**”:
main()